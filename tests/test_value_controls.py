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


def test_explicit_relative_from_captures_both_endpoints_before_delayed_playback():
    manager, value = TweenManager(), [(10.0, 20.0)]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), (20.0, 40.0), 1)
    tween.From((5.0, 6.0), set_immediately=False, relative=True).SetDelay(0.2).SetEase(Ease.Linear)
    assert value[0] == (10, 20)
    value[0] = (100.0, 200.0)
    manager.Update(0.1)
    assert value[0] == (100, 200)
    manager.Update(0.1)
    assert value[0] == (15, 26)
    manager.Update(0.5)
    assert value[0] == pytest.approx((22.5, 43))


def test_explicit_numeric_from_retains_float_sampling_and_can_configure_speed_after_capture():
    manager, value = TweenManager(), [10.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 5)
    tween.From(5).SetSpeedBased().SetEase(Ease.Linear)
    assert value[0] == 5
    tween.ForceInit().ForceInit()
    assert tween.Duration() == pytest.approx(3)
    manager.Update(0.1)
    assert value[0] == pytest.approx(5.5)


def test_from_without_an_explicit_start_can_defer_target_capture_until_playback():
    manager, value = TweenManager(), [10.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 1)
    tween.From(set_immediately=False).SetDelay(1).SetEase(Ease.Linear)
    value[0] = 30.0
    manager.Update(1.5)
    assert value[0] == pytest.approx(25)


@pytest.mark.parametrize("state", ["playing", "paused", "backwards"])
def test_change_values_rewinds_without_replaying_delay_or_start_callbacks(state):
    manager, value, events = TweenManager(), [0.0], []
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1)
    tween.SetDelay(0.5).SetEase(Ease.Linear).SetAutoKill(False)
    tween.OnStart(lambda: events.append("start")).OnPlay(lambda: events.append("play"))
    tween.OnRewind(lambda: events.append("rewind"))
    manager.Update(0.75)
    if state == "paused":
        tween.Pause()
    elif state == "backwards":
        tween.PlayBackwards()
    tween.ChangeEndValue(30.0, 2, snap_start_value=True)
    assert value[0] == 2.5 and tween.position == 0.5 and tween.Duration() == 2
    assert tween.IsPlaying() == (state == "playing")
    assert tween.IsBackwards() == (state == "backwards")
    manager.Update(0.2)
    assert value[0] == pytest.approx(5.25 if state == "playing" else 2.5)
    tween.ChangeStartValue(5.0, 0)
    assert value[0] == 5 and tween.Duration() == 2
    tween.ChangeValues(2.0, 6.0, 1)
    assert value[0] == 2 and tween.Duration() == 1
    assert events.count("start") == events.count("play") == 1
    assert "rewind" in events


def test_change_start_before_initialization_uses_the_new_relative_base_and_keeps_partial_delay():
    manager, value = TweenManager(), [10.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 1)
    tween.SetRelative().SetDelay(1).SetEase(Ease.Linear)
    manager.Update(0.3)
    tween.ChangeStartValue(5.0)
    assert tween.position == pytest.approx(0.3) and value[0] == 5
    manager.Update(0.7)
    assert value[0] == pytest.approx(5)
    manager.Update(0.5)
    assert value[0] == pytest.approx(15)


def test_change_speed_based_duration_is_recomputed_only_for_a_new_positive_speed():
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 2)
    tween.SetSpeedBased().SetEase(Ease.Linear).SetAutoKill(False)
    manager.Update(1)
    tween.ChangeEndValue(20.0)
    assert tween.Duration() == 5
    tween.ChangeEndValue(30.0, 3)
    assert tween.Duration() == 10
    tween.ChangeValues(10.0, 20.0, 2)
    assert tween.Duration() == 5
    tween.ForceInit()
    assert tween.Duration() == 5


def test_change_methods_leave_sequence_children_and_parent_timing_unchanged():
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).SetEase(Ease.Linear)
    sequence = manager.Sequence().Append(tween)
    tween.ChangeStartValue(50).ChangeEndValue(100, 4).ChangeValues(50, 100, 5)
    assert sequence.Duration() == 1
    manager.Update(0.5)
    assert value[0] == 5


def test_change_inside_an_update_callback_aborts_the_old_sample_and_respects_rewind_pause():
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).SetEase(Ease.Linear)
    tween.OnUpdate(lambda: tween.ChangeValues(20.0, 30.0)).OnRewind(tween.Pause)
    manager.Update(0.5)
    assert tween.position == 0 and value[0] == 20 and not tween.IsPlaying()


def test_change_end_boolean_argument_snaps_start_without_replacing_duration():
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 2).SetEase(Ease.Linear)
    manager.Update(1)
    tween.ChangeEndValue(20.0, True)
    assert value[0] == 5 and tween.Duration() == 2 and tween.IsPlaying()
    manager.Update(1)
    assert value[0] == pytest.approx(12.5)
