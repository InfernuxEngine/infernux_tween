import pytest

from infernux.lib import SceneManager, Vector3, quatf
from infernux_tween import AxisConstraint, DOTween, Ease, LoopType, Path, PathType, ShortcutExtensions as S


@pytest.fixture
def target():
    manager = SceneManager.instance()
    scene = manager.create_scene("Path playback")
    obj = scene.create_game_object("Mover")
    yield obj.transform
    DOTween.Clear()
    manager.unload_scene(scene)


def test_linear_path_uses_distance_not_waypoint_count_and_notifies(target):
    events = []
    tween = S.DOLocalPath(target, [(1, 0, 0), (1, 3, 0)], 2).SetEase(Ease.Linear).OnWaypointChange(events.append)
    DOTween.Update(1)
    assert tuple(target.local_position) == pytest.approx((1, 1, 0))
    assert events == [0, 1]
    assert tween.PathLength() == 4
    DOTween.Update(1)
    assert tuple(target.local_position) == (1, 3, 0) and events[-1] == 2


def test_curves_have_exact_endpoints_and_closed_catmull_is_continuous():
    bezier = Path((0, 0, 0), [(2, 0, 0), (0, 2, 0), (2, 2, 0)], PathType.CubicBezier, 64)
    assert tuple(bezier.point(0.5)) == pytest.approx((1, 1.5, 0), abs=0.001)
    assert bezier.length == pytest.approx(4, rel=0.001)
    curve = Path((0, 0, 0), [(1, 0, 0), (1, 1, 0), (0, 1, 0)], PathType.CatmullRom, 64, closed=True)
    assert tuple(curve.point(0)) == tuple(curve.point(1))
    for i in range(3):
        assert tuple(curve.evaluate(i+1)) == tuple(curve.points[i+1])
    left = curve.point(0.0001) - curve.point(0)
    right = curve.point(1) - curve.point(0.9999)
    assert Vector3.angle(left, right) < 1


def test_relative_speed_path_locking_seek_and_orientation(target):
    target.position = Vector3(2, 3, 4)
    tween = S.DOPath(target, [(3, 8, 0)], 1).SetRelative().SetOptions(lock_position=AxisConstraint.Y)
    tween.SetLookAt(0.01).SetSpeedBased().SetAutoKill(False).SetEase(Ease.Linear)
    DOTween.Update(1)
    assert tuple(target.position) == pytest.approx((3, 3, 4))
    assert tween.Duration() == 3
    assert quatf.angle(target.rotation, quatf.look_rotation(Vector3(1, 0, 0))) < 0.01
    tween.Goto(0.5)
    assert tuple(target.position) == pytest.approx((2.5, 3, 4))


@pytest.mark.parametrize("local", [False, True])
def test_incremental_path_preserves_lookahead_direction_in_later_loops(target, local):
    create = S.DOLocalPath if local else S.DOPath
    tween = create(target, [(10, 0, 0)], 1).SetLoops(2, LoopType.Incremental)
    tween.SetEase(Ease.Linear).SetLookAt(0.01).SetAutoKill(False)
    expected_rotation = quatf.look_rotation(Vector3(1, 0, 0))
    for clock, position in ((0.5, 5), (1.5, 15), (2, 20)):
        tween.Goto(clock)
        assert tuple(target.local_position if local else target.position) == pytest.approx((position, 0, 0))
        assert quatf.angle(target.local_rotation if local else target.rotation, expected_rotation) < 0.01


def test_quaternion_rotation_from_and_speed_use_shortest_arc(target):
    end = quatf.euler(0, 90, 0)
    tween = S.DOLocalRotateQuaternion(target, end, 45).SetSpeedBased().SetEase(Ease.Linear)
    DOTween.Update(1)
    assert quatf.angle(target.local_rotation, end) == pytest.approx(45, abs=0.001)
    assert tween.Duration() == pytest.approx(2)
    tween.Kill()
    target.local_rotation = quatf.identity()
    DOTween.To(lambda: target.local_rotation, lambda value: setattr(target, "local_rotation", value), end, 1).From().SetEase(Ease.Linear)
    assert quatf.angle(target.local_rotation, end) < 0.01
    DOTween.Update(1)
    assert quatf.angle(target.local_rotation, quatf.identity()) < 0.01
