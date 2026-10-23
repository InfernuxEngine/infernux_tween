import pytest

from infernux.components import FieldType, get_serialized_fields
from infernux.engine.interaction.previews import PreviewService
from infernux.lib import SceneManager, Vector3
from infernux.ui import UIImage
from infernux_tween import Ease, LoopType
import infernux_tween as tween_api
from runtime.TweenAuthoring import TweenAuthoring
from runtime.TweenAnimation import AnimationType, TweenAnimation, TargetKind
from runtime.TweenPath import TweenPath
from runtime.TweenVisualManager import ActivationAction, TweenVisualManager
from test_links import owner


def test_component_is_idle_in_edit_mode_and_controls_the_native_target(owner):
    scene, obj = owner
    animation = obj.add_component(TweenAnimation)
    assert animation.get_tween() is None and tween_api.total_active_tweens() == 0
    animation.auto_play, animation.ease = False, Ease.LINEAR
    animation.end_vector = (4, 0, 0)
    completed = []
    animation.on_complete.add_listener(lambda: completed.append(True))
    SceneManager.instance().play()
    assert animation.create_tween() is None
    tween = animation.get_tween()
    assert animation.get_tweens() == [tween] and not tween.is_playing()
    animation.do_play()
    tween_api.update(0.5)
    assert obj.transform.local_position.x == 2
    assert animation.do_rewind() is None
    assert animation.do_restart() is None
    tween_api.update(1)
    assert completed == [True] and obj.transform.local_position.x == 4
    scene.destroy_game_object(obj)
    scene.process_pending_destroys()
    assert not tween.is_active() and not tween_api.total_active_tweens()


def test_visual_configuration_uses_serialized_references_and_rejects_invalid_pairings(owner):
    _, obj = owner
    animation = obj.add_component(TweenAnimation)
    image = obj.add_component(UIImage)
    animation.animation_type, animation.target_kind = AnimationType.COLOR, TargetKind.IMAGE
    animation.end_color, animation.ease = [1, 0, 0, 0], Ease.LINEAR
    animation.create_tween()
    tween_api.update(0.5)
    assert image.color == pytest.approx([1, 0.5, 0.5, 0.5])
    animation.do_kill()
    animation.target_kind = TargetKind.TRANSFORM
    with pytest.raises(ValueError, match="does not animate"):
        animation.create_tween()
    animation.animation_type, animation.loops = AnimationType.LOCAL_MOVE, 0
    animation.create_tween()
    created = animation.get_tween()
    assert created.duration() == animation.duration
    created.kill()
    assert not tween_api.total_active_tweens()
    assert get_serialized_fields(TweenAnimation)['target'].field_type == FieldType.GAME_OBJECT
    assert get_serialized_fields(TweenPath)['waypoints'].element_type == FieldType.VEC3


def test_relative_path_waypoints_round_trip_under_a_transformed_parent(owner):
    scene, obj = owner
    parent = scene.create_game_object('Path parent')
    parent.transform.position = Vector3(10, 20, 0)
    parent.transform.euler_angles = Vector3(0, 0, 90)
    obj.set_parent(parent)
    obj.transform.local_position = Vector3(2, 0, 0)
    path = obj.add_component(TweenPath)
    path.local, path.relative = True, True
    path.waypoints = [(3, 4, 0)]
    world = path.world_waypoint(0)
    assert tuple(world) == pytest.approx((6, 25, 0), abs=0.00001)
    assert path.waypoint_from_world(world) == pytest.approx((3, 4, 0), abs=0.00001)
    drawn = path.draw_points()
    assert drawn is path.draw_points() and drawn[-1] == pytest.approx((6, 25, 0), abs=0.00001)
    path.ease = Ease.LINEAR
    path.create_tween()
    tween_api.update(1)
    assert tuple(obj.transform.local_position) == pytest.approx((5, 4, 0))


def test_preview_is_local_to_its_scope_and_restores_pose_and_runtime_state(owner, monkeypatch):
    from infernux.application import Application
    monkeypatch.setattr(Application, 'is_headless', staticmethod(lambda: True))
    _, obj = owner
    animation = obj.add_component(TweenAnimation)
    animation.end_vector, animation.ease = (8, 0, 0), Ease.LINEAR
    animation.loops, animation.loop_type = 2, LoopType.YOYO
    events = []
    animation.on_start.add_listener(lambda: events.append('start'))
    previews = PreviewService()
    scope = previews.begin('tween-preview')
    tween = animation.begin_preview(scope)
    animation._preview_manager.manual_update(0.5, 0.5)
    assert obj.transform.local_position.x == 4 and not events
    assert tween_api.total_active_tweens() == 0
    scope.close()
    assert obj.transform.local_position.x == 0 and not tween.is_active()
    assert animation._tween is animation._preview_manager is animation._preview_registration is None
    from infernux.components.builtin import Camera
    camera = obj.add_component(Camera)
    background = list(camera.background_color)
    animation.animation_type, animation.target_kind = AnimationType.COLOR, TargetKind.CAMERA
    animation.end_color = [0.8, 0.2, 0.4, 0.5]
    scope = previews.begin('camera-preview')
    animation.begin_preview(scope)
    animation._preview_manager.manual_update(0.5, 0.5)
    assert camera.background_color != background
    scope.close()
    assert camera.background_color == pytest.approx(background)


def test_visual_manager_handles_native_pool_activation_without_idle_updates(owner):
    _, obj = owner
    animation = obj.add_component(TweenAnimation)
    animation.end_vector, animation.ease = (4, 0, 0), Ease.LINEAR
    manager = obj.add_component(TweenVisualManager)
    assert manager.on_enable_action == ActivationAction.RESTART
    assert animation.get_tween() is None
    SceneManager.instance().play()
    tween_api.update(0.25)
    assert obj.transform.local_position.x == 1
    obj.active = False
    tween_api.update(5)
    assert obj.transform.local_position.x == 1 and not animation.get_tween().is_playing()
    obj.active = True
    tween_api.update(0.5)
    assert obj.transform.local_position.x == 2


def test_rigidbody_euler_rotation_uses_move_rotation_in_fixed_clock(owner, monkeypatch):
    from infernux.components.builtin import Rigidbody
    from infernux.lib import quatf
    from infernux_tween import shortcuts as S, UpdateType
    _, obj = owner
    body = obj.add_component(Rigidbody)
    rotations = []
    monkeypatch.setattr(Rigidbody, 'move_rotation', lambda self, value: rotations.append(value))
    tween = S.do_rotate(body, (0, 90, 0), 1).set_ease(Ease.LINEAR)
    assert tween.update_type == UpdateType.FIXED
    tween_api.update(0.5)
    assert not rotations
    tween_api.update(0.5, update_type=UpdateType.FIXED)
    assert quatf.angle(rotations[-1], quatf.identity()) == pytest.approx(45, abs=0.001)
    tween.kill()


def test_external_authored_target_destruction_retires_a_paused_tween(owner):
    scene, obj = owner
    target = scene.create_game_object('Separate target')
    animation = obj.add_component(TweenAnimation)
    animation.target, animation.auto_play = target, False
    SceneManager.instance().play()
    animation.create_tween()
    tween = animation.get_tween()
    assert tween.is_active() and not tween.is_playing()
    scene.destroy_game_object(target)
    scene.process_pending_destroys()
    assert obj and not tween.is_active()


def test_target_inference_is_unique_at_creation_and_ambiguity_requires_selection(owner):
    from infernux.components.builtin import Light, Rigidbody
    from infernux.ui import UIText
    _, obj = owner
    text = obj.add_component(UIText)
    animation = obj.add_component(TweenAnimation)
    animation.animation_type = AnimationType.COLOR
    assert animation.target_kind == TargetKind.AUTO
    assert animation.create_tween() is None
    assert animation.get_tween().target is obj
    assert animation._resolve_target() is text
    animation.do_kill()
    obj.add_component(Light)
    with pytest.raises(ValueError, match="Select Target Component"):
        animation.create_tween()
    assert tween_api.total_active_tweens() == 0
    animation.animation_type = AnimationType.MOVE
    body = obj.add_component(Rigidbody)
    animation.create_tween()
    tween = animation.get_tween()
    assert tween.target is obj and tween.update_type.name == "FIXED"
    assert animation._resolve_target() is body


def test_authored_group_id_next_and_recreation_controls_use_their_declared_scope(owner):
    scene, obj = owner
    first, second = obj.add_component(TweenAnimation), obj.add_component(TweenAnimation)
    elsewhere = scene.create_game_object('Other group')
    third = elsewhere.add_component(TweenAnimation)
    for animation in (first, second, third):
        animation.auto_play, animation.auto_kill, animation.ease = False, False, Ease.LINEAR
        animation.tween_id = 'move'
    first.end_vector = third.end_vector = (4, 0, 0)
    second.animation_type, second.end_vector, second.tween_id = AnimationType.SCALE, (2, 2, 2), 'scale'
    SceneManager.instance().play()
    tweens = [animation.get_tween() for animation in (first, second, third)]
    assert first.do_play() is None
    assert [tween.is_playing() for tween in tweens] == [True, True, False]
    first.do_pause()
    first.do_play_by_id('move')
    assert [tween.is_playing() for tween in tweens] == [True, False, False]
    first.do_pause_all_by_id('move')
    first.do_play_all_by_id('move')
    assert [tween.is_playing() for tween in tweens] == [True, False, True]
    first.do_goto_and_pause(0.5)
    assert obj.transform.local_position.x == 2 and tuple(obj.transform.local_scale) == (1.5, 1.5, 1.5)
    first.do_rewind_and_play_next()
    assert [tween.is_playing() for tween in tweens] == [True, False, True]
    first.do_play_next()
    assert tweens[1].is_playing()
    first.relative = True
    obj.transform.local_position = Vector3(10, 0, 0)
    first.do_restart(from_here=True)
    tween_api.update(1)
    assert obj.transform.local_position.x == 14
    first.create_tween(regenerate_if_exists=True, and_play=False)
    fresh = first.get_tween()
    assert fresh is not tweens[0] and not tweens[0].is_active() and not fresh.is_playing()
    first.recreate_tween_and_play()
    assert first.get_tween().is_playing() and not fresh.is_active()
    first.do_kill()
    assert not first.get_tween().is_active() and not second.get_tween().is_active()
    first.do_restart()
    assert not first.get_tween().is_active()
    first.set_animation_target(elsewhere.transform, False)
    first.create_tween(True, False)
    assert first.get_tween().target is obj
    first.do_play()
    assert not third.get_tween().is_playing()


def test_rewind_restores_overlapping_properties_in_reverse_component_order(owner):
    _, obj = owner
    first, second = obj.add_component(TweenAnimation), obj.add_component(TweenAnimation)
    first.ease = second.ease = Ease.LINEAR
    first.end_vector, second.end_vector = (10, 0, 0), (20, 0, 0)
    first.create_tween()
    first.get_tween().goto(0.5)
    second.create_tween()
    second.get_tween().goto(0.5)
    assert obj.transform.local_position.x == 12.5
    third = obj.add_component(TweenAnimation)
    third.end_vector = (50, 0, 0)
    third.create_tween()
    assert not third.get_tween().is_initialized()
    first.do_rewind()
    assert obj.transform.local_position.x == 0
    path = obj.add_component(TweenPath)
    path.waypoints = [(3, 0, 0)]
    path.create_tween()
    assert first.get_tweens() == [animation.get_tween() for animation in (first, second, third)]
