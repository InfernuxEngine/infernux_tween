import pytest

from infernux.components import FieldType, get_serialized_fields
from infernux.engine.interaction.previews import PreviewService
from infernux.lib import Vector3
from infernux.ui import UIImage
from infernux_tween import DOTween, Ease, LoopType
from infernux_tween.authoring import TweenAuthoring
from DOTweenAnimation import AnimationType, DOTweenAnimation, TargetKind
from DOTweenPath import DOTweenPath
from DOTweenVisualManager import ActivationAction, DOTweenVisualManager
from test_links import owner


def test_component_is_idle_in_edit_mode_and_controls_the_native_target(owner):
    scene, obj = owner
    animation = obj.add_component(DOTweenAnimation)
    assert animation.GetTween() is None and DOTween.TotalActiveTweens() == 0
    animation.auto_play, animation.ease = False, Ease.Linear
    animation.end_vector = (4, 0, 0)
    completed = []
    animation.on_complete.add_listener(lambda: completed.append(True))
    tween = animation.CreateTween()
    assert animation.GetTweens() == [tween] and not tween.IsPlaying()
    animation.DOPlay()
    DOTween.Update(0.5)
    assert obj.transform.local_position.x == 2
    animation.DORewind().DORestart()
    DOTween.Update(1)
    assert completed == [True] and obj.transform.local_position.x == 4
    scene.destroy_game_object(obj)
    scene.process_pending_destroys()
    assert not tween.IsActive() and not DOTween.TotalActiveTweens()


def test_visual_configuration_uses_serialized_references_and_rejects_invalid_pairings(owner):
    _, obj = owner
    animation = obj.add_component(DOTweenAnimation)
    image = obj.add_component(UIImage)
    animation.animation_type, animation.target_kind = AnimationType.Color, TargetKind.Image
    animation.end_color, animation.ease = [1, 0, 0, 0], Ease.Linear
    animation.CreateTween()
    DOTween.Update(0.5)
    assert image.color == pytest.approx([1, 0.5, 0.5, 0.5])
    animation.DOKill()
    animation.target_kind = TargetKind.Transform
    with pytest.raises(ValueError, match="does not animate"):
        animation.CreateTween()
    animation.animation_type, animation.loops = AnimationType.LocalMove, 0
    with pytest.raises(ValueError, match="Loops"):
        animation.CreateTween()
    assert not DOTween.TotalActiveTweens()
    assert get_serialized_fields(DOTweenAnimation)['target'].field_type == FieldType.GAME_OBJECT
    assert get_serialized_fields(DOTweenPath)['waypoints'].element_type == FieldType.VEC3


def test_relative_path_waypoints_round_trip_under_a_transformed_parent(owner):
    scene, obj = owner
    parent = scene.create_game_object('Path parent')
    parent.transform.position = Vector3(10, 20, 0)
    parent.transform.euler_angles = Vector3(0, 0, 90)
    obj.set_parent(parent)
    obj.transform.local_position = Vector3(2, 0, 0)
    path = obj.add_component(DOTweenPath)
    path.local, path.relative = True, True
    path.waypoints = [(3, 4, 0)]
    world = path.WorldWaypoint(0)
    assert tuple(world) == pytest.approx((6, 25, 0), abs=0.00001)
    assert path.WaypointFromWorld(world) == pytest.approx((3, 4, 0), abs=0.00001)
    drawn = path.DrawPoints()
    assert drawn is path.DrawPoints() and drawn[-1] == pytest.approx((6, 25, 0), abs=0.00001)
    path.ease = Ease.Linear
    path.CreateTween()
    DOTween.Update(1)
    assert tuple(obj.transform.local_position) == pytest.approx((5, 4, 0))


def test_preview_is_local_to_its_scope_and_restores_pose_and_runtime_state(owner, monkeypatch):
    from infernux.application import Application
    monkeypatch.setattr(Application, 'is_headless', staticmethod(lambda: True))
    _, obj = owner
    animation = obj.add_component(DOTweenAnimation)
    animation.end_vector, animation.ease = (8, 0, 0), Ease.Linear
    animation.loops, animation.loop_type = 2, LoopType.Yoyo
    events = []
    animation.on_start.add_listener(lambda: events.append('start'))
    previews = PreviewService()
    scope = previews.begin('tween-preview')
    tween = animation.BeginPreview(scope)
    animation._preview_manager.ManualUpdate(0.5, 0.5)
    assert obj.transform.local_position.x == 4 and not events
    assert DOTween.TotalActiveTweens() == 0
    scope.close()
    assert obj.transform.local_position.x == 0 and not tween.IsActive()
    assert animation._tween is animation._preview_manager is animation._preview_registration is None
    from infernux.components.builtin import Camera
    camera = obj.add_component(Camera)
    background = list(camera.background_color)
    animation.animation_type, animation.target_kind = AnimationType.Color, TargetKind.Camera
    animation.end_color = [0.8, 0.2, 0.4, 0.5]
    scope = previews.begin('camera-preview')
    animation.BeginPreview(scope)
    animation._preview_manager.ManualUpdate(0.5, 0.5)
    assert camera.background_color != background
    scope.close()
    assert camera.background_color == pytest.approx(background)


def test_visual_manager_handles_native_pool_activation_without_idle_updates(owner, monkeypatch):
    from types import SimpleNamespace
    import DOTweenVisualManager as module
    monkeypatch.setattr(module, 'SceneManager', SimpleNamespace(instance=lambda: SimpleNamespace(is_playing=lambda: True)))
    _, obj = owner
    animation = obj.add_component(DOTweenAnimation)
    animation.end_vector, animation.ease = (4, 0, 0), Ease.Linear
    manager = obj.add_component(DOTweenVisualManager)
    assert manager.on_enable_action == ActivationAction.Restart
    DOTween.Update(0.25)
    assert obj.transform.local_position.x == 1
    obj.active = False
    DOTween.Update(5)
    assert obj.transform.local_position.x == 1 and not animation.GetTween().IsPlaying()
    obj.active = True
    DOTween.Update(0.5)
    assert obj.transform.local_position.x == 2


def test_rigidbody_euler_rotation_uses_move_rotation_in_fixed_clock(owner, monkeypatch):
    from infernux.components.builtin import Rigidbody
    from infernux.lib import quatf
    from infernux_tween import ShortcutExtensions as S, UpdateType
    _, obj = owner
    body = obj.add_component(Rigidbody)
    rotations = []
    monkeypatch.setattr(Rigidbody, 'move_rotation', lambda self, value: rotations.append(value))
    tween = S.DORotate(body, (0, 90, 0), 1).SetEase(Ease.Linear)
    assert tween.update_type == UpdateType.Fixed
    DOTween.Update(0.5)
    assert not rotations
    DOTween.Update(0.5, update_type=UpdateType.Fixed)
    assert quatf.angle(rotations[-1], quatf.identity()) == pytest.approx(45, abs=0.001)
    tween.Kill()


def test_external_authored_target_destruction_retires_a_paused_tween(owner, monkeypatch):
    from types import SimpleNamespace
    import infernux_tween.authoring as module
    scene, obj = owner
    target = scene.create_game_object('Separate target')
    animation = obj.add_component(DOTweenAnimation)
    animation.target, animation.auto_play = target, False
    monkeypatch.setattr(module, 'SceneManager', SimpleNamespace(instance=lambda: SimpleNamespace(is_playing=lambda: True)))
    tween = animation.CreateTween()
    assert tween.IsActive() and not tween.IsPlaying()
    scene.destroy_game_object(target)
    scene.process_pending_destroys()
    assert obj and not tween.IsActive()


def test_target_inference_is_unique_at_creation_and_ambiguity_requires_selection(owner):
    from infernux.components.builtin import Light, Rigidbody
    from infernux.ui import UIText
    _, obj = owner
    text = obj.add_component(UIText)
    animation = obj.add_component(DOTweenAnimation)
    animation.animation_type = AnimationType.Color
    assert animation.target_kind == TargetKind.Auto
    assert animation.CreateTween().target is text
    animation.DOKill()
    obj.add_component(Light)
    with pytest.raises(ValueError, match="Select Target Component"):
        animation.CreateTween()
    assert DOTween.TotalActiveTweens() == 0
    animation.animation_type = AnimationType.Move
    body = obj.add_component(Rigidbody)
    tween = animation.CreateTween()
    assert tween.target is body and tween.update_type.name == "Fixed"
