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
