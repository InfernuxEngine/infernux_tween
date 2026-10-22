import asyncio

import pytest

from infernux.lib import Vector3
from infernux_tween import AxisConstraint, Ease, LoopType, TweenManager


def test_speed_based_capture_and_zero_distance():
    manager, value = TweenManager(), [(1.0, 2.0)]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), (4, 6), 2).SetSpeedBased().SetEase(Ease.Linear)
    manager.Update(1)
    assert value[0] == pytest.approx((2.2, 3.6))
    assert tween.Duration() == 2.5
    manager.Update(1.5)
    assert value[0] == (4, 6) and not tween.IsActive()
    still = manager.To(lambda: 4.0, lambda item: None, 4.0, 3).SetSpeedBased()
    manager.Update(0.01)
    assert not still.IsActive()


def test_integer_and_constrained_native_vector_keep_external_axes():
    manager, integer, vector = TweenManager(), [1], [Vector3(2, 3, 4)]
    manager.To(lambda: integer[0], lambda value: integer.__setitem__(0, value), 6, 1).SetEase(Ease.Linear)
    tween = manager.To(lambda: vector[0], lambda value: vector.__setitem__(0, value), Vector3(8, 10, 12), 1)
    tween.SetEase(Ease.Linear).SetOptions(AxisConstraint.Y, snapping=True)
    vector[0] = Vector3(20, 3, 40)
    manager.Update(0.5)
    assert integer[0] == 4 and type(integer[0]) is int
    assert tuple(vector[0]) == (20, 6, 40)


def test_smooth_rewind_skips_restart_loops_and_preserves_yoyo_pose():
    for kind in (LoopType.Restart, LoopType.Yoyo):
        manager, value = TweenManager(), [0.0]
        tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).SetEase(Ease.Linear)
        tween.SetLoops(4, kind).SetAutoKill(False)
        manager.Update(1.25)
        previous = value[0]
        tween.SmoothRewind()
        assert value[0] == pytest.approx(previous)
        manager.Update(1)
        assert value[0] == 0 and not tween.IsPlaying()


def test_coroutine_and_async_waits_keep_user_callbacks_and_release_on_kill():
    async def scenario():
        manager, value, events = TweenManager(), [0.0], []
        tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1)
        tween.SetDelay(0.2).SetLoops(2).SetAutoKill(False).OnComplete(lambda: events.append("done"))
        start = tween.WaitForStart()
        position = asyncio.create_task(tween.AsyncWaitForPosition(0.5))
        complete = asyncio.create_task(tween.AsyncWaitForCompletion())
        killed = asyncio.create_task(tween.AsyncWaitForKill())
        await asyncio.sleep(0)
        assert not start._is_ready()
        manager.Update(0.75)
        await asyncio.sleep(0)
        assert start._is_ready() and position.done() and not complete.done()
        manager.Update(1.5)
        await complete
        assert events == ["done"] and not killed.done()
        tween.Kill()
        await killed
        assert not tween._waiters
    asyncio.run(scenario())


def test_diagnostics_count_roots_and_distinguish_paused_and_manual_clocks():
    from infernux_tween import UpdateType
    manager = TweenManager()
    manager.Sequence().Append(manager.To(lambda: 0, lambda value: None, 1, 1))
    manual = manager.To(lambda: 0, lambda value: None, 1, 1).SetUpdate(UpdateType.Manual).Pause()
    diagnostics = manager.GetDiagnostics()
    assert diagnostics['active'] == 2 and diagnostics['playing'] == 1
    assert diagnostics['phases']['Normal'] == {'active': 1, 'playing': 1}
    assert diagnostics['phases']['Manual'] == {'active': 1, 'playing': 0}
    manual.Play()
    manager.ManualUpdate(1, 1)
    assert manager.GetDiagnostics()['active'] == 1
    manager.Clear()
