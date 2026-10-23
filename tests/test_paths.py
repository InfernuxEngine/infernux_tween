import pytest

from infernux.lib import SceneManager, Vector3, quatf
from infernux_tween import AxisConstraint, Ease, LoopType, Path, PathMode, PathType, UpdateType, shortcuts as S
import infernux_tween as tween_api


@pytest.fixture
def target():
    manager = SceneManager.instance()
    scene = manager.create_scene("Path playback")
    obj = scene.create_game_object("Mover")
    yield obj.transform
    tween_api.clear()
    manager.unload_scene(scene)


def test_linear_path_uses_distance_not_waypoint_count_and_notifies(target):
    events = []
    tween = S.do_local_path(target, [(1, 0, 0), (1, 3, 0)], 2).set_ease(Ease.LINEAR).on_waypoint_change(events.append)
    tween_api.update(1)
    assert tuple(target.local_position) == pytest.approx((1, 1, 0))
    assert events == [0, 1]
    assert tween.path_length() == 4
    tween_api.update(1)
    assert tuple(target.local_position) == (1, 3, 0) and events[-1] == 2


def test_curves_have_exact_endpoints_and_closed_catmull_is_continuous():
    bezier = Path((0, 0, 0), [(2, 0, 0), (0, 2, 0), (2, 2, 0)], PathType.CUBIC_BEZIER, 64)
    assert tuple(bezier.point(0.5)) == pytest.approx((1, 1.5, 0), abs=0.001)
    assert bezier.length == pytest.approx(4, rel=0.001)
    curve = Path((0, 0, 0), [(1, 0, 0), (1, 1, 0), (0, 1, 0)], PathType.CATMULL_ROM, 64, closed=True)
    assert tuple(curve.point(0)) == tuple(curve.point(1))
    for i in range(3):
        assert tuple(curve.evaluate(i+1)) == tuple(curve.points[i+1])
    left = curve.point(0.0001) - curve.point(0)
    right = curve.point(1) - curve.point(0.9999)
    assert Vector3.angle(left, right) < 1


def test_relative_speed_path_locking_seek_and_orientation(target):
    target.position = Vector3(2, 3, 4)
    tween = S.do_path(target, [(3, 8, 0)], 1).set_relative().set_options(lock_position=AxisConstraint.Y)
    tween.set_look_at(0.01).set_speed_based().set_auto_kill(False).set_ease(Ease.LINEAR)
    tween_api.update(1)
    assert tuple(target.position) == pytest.approx((3, 3, 4))
    assert tween.duration() == 3
    assert quatf.angle(target.rotation, quatf.look_rotation(Vector3(1, 0, 0))) < 0.01
    tween.goto(0.5)
    assert tuple(target.position) == pytest.approx((2.5, 3, 4))


@pytest.mark.parametrize("local", [False, True])
def test_incremental_path_preserves_lookahead_direction_in_later_loops(target, local):
    create = S.do_local_path if local else S.do_path
    tween = create(target, [(10, 0, 0)], 1).set_loops(2, LoopType.INCREMENTAL)
    tween.set_ease(Ease.LINEAR).set_look_at(0.01).set_auto_kill(False)
    expected_rotation = quatf.look_rotation(Vector3(1, 0, 0))
    for clock, position in ((0.5, 5), (1.5, 15), (2, 20)):
        tween.goto(clock)
        assert tuple(target.local_position if local else target.position) == pytest.approx((position, 0, 0))
        assert quatf.angle(target.local_rotation if local else target.rotation, expected_rotation) < 0.01


def test_quaternion_rotation_from_and_speed_use_shortest_arc(target):
    end = quatf.euler(0, 90, 0)
    tween = S.do_local_rotate_quaternion(target, end, 45).set_speed_based().set_ease(Ease.LINEAR)
    tween_api.update(1)
    assert quatf.angle(target.local_rotation, end) == pytest.approx(45, abs=0.001)
    assert tween.duration() == pytest.approx(2)
    tween.kill()
    target.local_rotation = quatf.identity()
    tween_api.to(lambda: target.local_rotation, lambda value: setattr(target, "local_rotation", value), end, 1).from_().set_ease(Ease.LINEAR)
    assert quatf.angle(target.local_rotation, end) < 0.01
    tween_api.update(1)
    assert quatf.angle(target.local_rotation, quatf.identity()) < 0.01


def test_explicit_quaternion_from_captures_relative_rotation_in_target_order(target):
    current, first, end = quatf.euler(30, 0, 0), quatf.euler(0, 40, 0), quatf.euler(0, 0, 70)
    target.local_rotation = current
    tween = S.do_local_rotate_quaternion(target, end, 1).from_(first, False, True).set_auto_kill(False)
    assert quatf.angle(target.local_rotation, current) < 0.01
    target.local_rotation = quatf.identity()
    tween.goto(0)
    assert quatf.angle(target.local_rotation, current * first) < 0.01
    tween.complete()
    assert quatf.angle(target.local_rotation, current * end) < 0.01
    tween.change_values(first, end).complete()
    assert quatf.angle(target.local_rotation, end) < 0.01


def test_look_at_typed_keywords_custom_axes_and_stable_up(target):
    look_target = target.game_object.scene.create_game_object("Look target").transform
    look_target.position = Vector3(5, 0, 10)
    create = lambda: S.do_path(target, [Vector3(0, 0, 10)], 1).set_ease(Ease.LINEAR)
    for name, value in (("look_ahead", 0.01), ("look_at_position", look_target.position),
                        ("look_at_transform", look_target)):
        target.position, target.rotation = Vector3(0, 0, 0), quatf.identity()
        tween = create().set_look_at(**{name: value}, forward_direction=Vector3(1, 0, 0), up=Vector3(0, 1, 0))
        tween.goto(0.5)
        direction = Vector3(0, 0, 1) if name == "look_ahead" else look_target.position-target.position
        expected = quatf.look_rotation(direction) * quatf.look_rotation(Vector3(1, 0, 0))
        assert quatf.angle(target.rotation, expected) < 0.01
        tween.kill()
    target.position, target.rotation = Vector3(0, 0, 0), quatf.euler(0, 0, 35)
    tween = create().set_look_at(look_at_position=Vector3(5, 0, 10), stable_z_rotation=True)
    tween.goto(0.5)
    assert quatf.angle(target.rotation, quatf.look_rotation(Vector3(5, 0, 5))) < 0.01
    for kwargs in ({"look_ahead": True}, {"look_at_position": (1, 0, 0)},
                   {"look_ahead": 0.1, "stable_z_rotation": True, "up": Vector3(0, 1, 0)}):
        with pytest.raises(TypeError):
            create().set_look_at(**kwargs)


def test_two_dimensional_path_modes_use_xy_and_sidescroller_flip(target):
    for mode, point, expected in (
        (PathMode.TOP_DOWN2_D, Vector3(0, 2, 0), quatf.euler(0, 0, 90)),
        (PathMode.SIDESCROLLER2_D, Vector3(0, 2, 0), quatf.euler(0, 0, 90)),
        (PathMode.TOP_DOWN2_D, Vector3(-2, 0, 0), quatf.euler(0, 0, 180)),
        (PathMode.SIDESCROLLER2_D, Vector3(-2, 0, 0), quatf.euler(0, 180, 0)),
    ):
        target.position, target.rotation = Vector3(0, 0, 0), quatf.identity()
        tween = S.do_path(target, [point], 1, path_mode=mode).set_look_at(0.01)
        tween.goto(1)
        assert quatf.angle(target.rotation, expected) < 0.01
        tween.kill()


def test_local_path_orientation_uses_world_direction_and_fixed_world_look_target(target):
    parent = target.game_object.scene.create_game_object("Scaled parent")
    parent.transform.position, parent.transform.local_scale = Vector3(5, 4, 3), Vector3(2, 3, 4)
    parent.transform.rotation = quatf.euler(0, 30, 0)
    target.game_object.set_parent(parent)
    target.local_position = Vector3(0, 0, 0)
    tween = S.do_local_path(target, [Vector3(1, 1, 0)], 1).set_ease(Ease.LINEAR).set_look_at(0.01)
    tween.goto(0.5)
    assert tuple(target.position) == pytest.approx(tuple(parent.transform.transform_point(Vector3(0.5, 0.5, 0))))
    expected = quatf.look_rotation(parent.transform.transform_vector(Vector3(1, 1, 0)), target.up)
    assert quatf.angle(target.rotation, expected) < 0.01
    tween.kill()
    aim = Vector3(10, 2, 8)
    tween = S.do_local_path(target, [Vector3(2, 2, 0)], 1).set_look_at(look_at_position=aim, stable_z_rotation=True)
    tween.goto(1)
    assert quatf.angle(target.rotation, quatf.look_rotation(aim-target.position)) < 0.01


def test_rigidbody_local_path_schedules_world_moves_in_fixed_update(target, monkeypatch):
    from infernux.components.builtin import Rigidbody

    parent = target.game_object.scene.create_game_object("Body parent")
    parent.transform.position, parent.transform.rotation = Vector3(10, 0, 0), quatf.euler(0, 90, 0)
    target.game_object.set_parent(parent)
    target.local_position = Vector3(1, 0, 0)
    body = target.game_object.add_component(Rigidbody)
    positions, rotations = [], []
    monkeypatch.setattr(Rigidbody, "move_position", lambda self, value: positions.append(value))
    monkeypatch.setattr(Rigidbody, "move_rotation", lambda self, value: rotations.append(value))
    tween = S.do_local_path(body, [Vector3(3, 0, 0)], 1).set_ease(Ease.LINEAR).set_look_at(0.01, True)
    assert tween.update_type == UpdateType.FIXED
    tween_api.update(0.5)
    assert not positions and not rotations
    tween_api.update(0.5, update_type=UpdateType.FIXED)
    assert tuple(positions[0]) == pytest.approx(tuple(parent.transform.transform_point(Vector3(2, 0, 0))))
    assert quatf.angle(rotations[0], quatf.look_rotation(parent.transform.transform_vector(Vector3(1, 0, 0)))) < 0.01


def test_path_options_draw_subdivisions_and_parent_incremental_loop(target):
    color = [0.2, 0.4, 0.6, 0.8]
    child = S.do_path(target, [Vector3(2, 5, 0)], 1, resolution=1, gizmo_color=color)
    child.set_options(AxisConstraint.Y).set_ease(Ease.LINEAR)
    root = tween_api.sequence().append(child).set_loops(3, LoopType.INCREMENTAL).set_auto_kill(False)
    root.goto(2.5)
    assert tuple(target.position) == pytest.approx((5, 0, 0))
    assert child.gizmo_color == color and child.path_length() == 2
    assert len(child.path_get_draw_points(4)) == 2
    assert tuple(child.path_get_draw_points(4)[-1]) == (2, 0, 0)
    curve = S.do_path(target, [Vector3(1, 1, 0), Vector3(2, 0, 0)], 1, PathType.CATMULL_ROM)
    assert len(curve.path_get_draw_points(4)) == 9
    with pytest.raises(TypeError):
        S.do_path(target, [Vector3(1, 0, 0)], 1).set_options()


@pytest.mark.parametrize("action", ["pause", "rewind", "kill", "parent_pause"])
def test_waypoint_callback_control_stops_remaining_dispatch_and_preserves_reentrant_seek(target, action):
    child = S.do_path(target, [Vector3(i, 0, 0) for i in (1, 2, 3)], 3).set_ease(Ease.LINEAR)
    root = tween_api.sequence().append(child) if action == "parent_pause" else child
    events = []

    def changed(index):
        events.append(index)
        if index == 1:
            getattr(root, "pause" if action == "parent_pause" else action)()

    child.on_waypoint_change(changed)
    tween_api.update(2.5)
    assert events == [0, 1]
    assert not root.is_playing()
    if action == "rewind":
        assert tuple(target.position) == (0, 0, 0) and root.elapsed() == 0
    elif action == "kill":
        assert not root.is_active()
    else:
        assert tuple(target.position) == (2.5, 0, 0) and root.elapsed() == 2.5
        root.play()
        tween_api.update(0.25)
        assert root.elapsed() == 2.75 and tuple(target.position) == (2.75, 0, 0)


def test_waypoint_callback_reverse_and_yoyo_wait_until_the_waypoint_is_reached(target):
    events = []
    tween = S.do_path(target, [Vector3(1, 0, 0), Vector3(2, 0, 0)], 2)
    tween.set_ease(Ease.LINEAR).set_auto_kill(False).set_loops(2, LoopType.YOYO).on_waypoint_change(events.append)
    tween_api.update(2)
    assert events == [0, 1, 2]
    tween_api.update(0.25)
    assert events == [0, 1, 2]
    tween_api.update(0.75)
    assert events == [0, 1, 2, 1]
    tween.goto(2).play_backwards()
    events.clear()
    tween_api.update(0.25)
    assert events == []
    tween_api.update(0.75)
    assert events == [1]


def test_goto_waypoint_uses_distance_current_yoyo_cycle_and_play_flag(target):
    tween = S.do_path(target, [Vector3(1, 0, 0), Vector3(1, 3, 0)], 4)
    tween.set_loops(2, LoopType.YOYO).set_ease(Ease.LINEAR).set_auto_kill(False)
    tween.goto_waypoint(1, and_play=True)
    assert tween.is_playing() and tween.elapsed() == 1 and tuple(target.position) == (1, 0, 0)
    tween.goto(5).goto_waypoint(1)
    assert not tween.is_playing() and tween.elapsed() == 7 and tuple(target.position) == (1, 0, 0)
    tween.goto_waypoint(999)
    assert tween.elapsed() == 4 and tuple(target.position) == (1, 3, 0)
