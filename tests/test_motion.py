import pytest

from infernux.lib import SceneManager, Vector3
from infernux_tween import DOTween, Ease, ShortcutExtensions as S


@pytest.fixture
def target():
    manager = SceneManager.instance()
    scene = manager.create_scene("Procedural motion")
    obj = scene.create_game_object("Mover")
    yield obj.transform
    DOTween.Clear()
    manager.unload_scene(scene)


def test_jump_has_multiple_arcs_and_exact_destination(target):
    tween = S.DOJump(target, (4, 2, 0), 3, 2, 1).SetAutoKill(False)
    tween.Goto(0.25)
    assert tuple(target.position) == pytest.approx((1, 3.5, 0))
    tween.Goto(0.5)
    assert tuple(target.position) == pytest.approx((2, 1, 0))
    tween.Goto(1)
    assert tuple(target.position) == (4, 2, 0)
    tween.Rewind()
    assert tuple(target.position) == (0, 0, 0)
    tween.Kill()
    target.position = Vector3(2, 3, 0)
    relative = S.DOJump(target, (4, 2, 0), 3, 2, 1).SetRelative()
    relative.Complete()
    assert tuple(target.position) == (6, 5, 0)


def test_punch_and_seeded_shake_seek_without_accumulation(target):
    target.local_position = Vector3(5, 7, 9)
    for tween in (S.DOPunchPosition(target, (2, 0, 0), 1), S.DOShakePosition(target, 1, seed=42)):
        tween.Pause().Goto(0.123)
        first = tuple(target.local_position)
        tween.Goto(0.9).Goto(0.123)
        assert tuple(target.local_position) == first
        tween.Goto(1)
        assert tuple(target.local_position) == (5, 7, 9)
        tween.Kill()


def test_blendable_displacements_preserve_external_motion_and_rewind_only_their_share(target):
    first = S.DOBlendableMoveBy(target, (4, 0, 0), 1).SetEase(Ease.Linear).SetAutoKill(False)
    second = S.DOBlendableMoveBy(target, (0, 6, 0), 1).SetEase(Ease.Linear).SetAutoKill(False)
    DOTween.Update(0.5)
    assert tuple(target.position) == (2, 3, 0)
    target.position += Vector3(0, 0, 10)
    DOTween.Update(0.5)
    assert tuple(target.position) == (4, 6, 10)
    first.Rewind()
    assert tuple(target.position) == (0, 6, 10)
    second.Rewind()
    assert tuple(target.position) == (0, 0, 10)


def test_spiral_seek_uses_authored_axis_and_contracts_back_to_its_origin(target):
    from infernux_tween import SpiralMode
    target.local_position = Vector3(2, 3, 4)
    tween = S.DOSpiral(target, 2, (0, 0, 1), SpiralMode.ExpandThenContract).SetAutoKill(False)
    tween.Goto(0.5)
    sampled = tuple(target.local_position)
    assert sampled != (2, 3, 4)
    tween.Goto(2)
    assert tuple(target.local_position) == pytest.approx((2, 3, 4))
    tween.Goto(0.5)
    assert tuple(target.local_position) == sampled
    tween.Kill()
    target.local_position = Vector3(0, 0, 0)
    axial = S.DOSpiral(target, 2, (1, 0, 0), depth=3).SetAutoKill(False)
    axial.Goto(1)
    assert target.local_position.x == pytest.approx(1.5)
    assert target.local_position.y**2+target.local_position.z**2 == pytest.approx(1)


def test_blendable_rotation_keeps_other_tweens_and_external_orientation(target):
    from infernux.lib import quatf
    first = S.DOBlendableRotateBy(target, (0, 0, 180), 1).SetEase(Ease.Linear).SetAutoKill(False)
    second = S.DOBlendableRotateBy(target, (0, 0, 90), 1).SetEase(Ease.Linear).SetAutoKill(False)
    DOTween.Update(0.5)
    assert quatf.angle(target.rotation, quatf.euler(0, 0, 135)) < 0.01
    target.rotation = quatf.euler(0, 0, 10)*target.rotation
    DOTween.Update(0.5)
    assert quatf.angle(target.rotation, quatf.euler(0, 0, 280)) < 0.01
    first.Rewind()
    second.Rewind()
    assert quatf.angle(target.rotation, quatf.euler(0, 0, 10)) < 0.01
