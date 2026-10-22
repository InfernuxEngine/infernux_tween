import pytest

from infernux_tween import Ease, LoopType, TweenManager, UpdateType


def value_tween(manager, end=10.0, duration=1.0):
    value = [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), end, duration).SetEase(Ease.Linear)
    return value, tween


@pytest.mark.parametrize("ease", list(Ease))
def test_easing_curves_have_exact_endpoints_and_finite_samples(ease):
    from math import isfinite
    from infernux_tween.ease import resolve_ease

    curve = resolve_ease(ease)
    assert curve(0) == pytest.approx(0)
    assert curve(1) == pytest.approx(1)
    assert all(isfinite(curve(i / 100)) for i in range(101))


def test_delay_capture_pause_restart_and_completion_callbacks():
    manager, events = TweenManager(), []
    value, tween = value_tween(manager)
    tween.SetDelay(0.5).SetAutoKill(False).OnStart(lambda: events.append("start"))
    tween.OnStepComplete(lambda: events.append("step")).OnComplete(lambda: events.append("complete"))
    manager.Update(0.25)
    value[0] = 2.0
    manager.Update(0.75)
    assert value[0] == pytest.approx(6)
    tween.Pause()
    manager.Update(4)
    assert value[0] == pytest.approx(6)
    tween.Play()
    manager.Update(0.5)
    assert value[0] == 10
    assert events == ["start", "step", "complete"]
    tween.Restart(include_delay=False)
    assert value[0] == 2
    manager.Update(1)
    assert events == ["start", "step", "complete", "step", "complete"]


@pytest.mark.parametrize("loop_type, expected", [(LoopType.Restart, 5), (LoopType.Yoyo, 5), (LoopType.Incremental, 15)])
def test_loop_sampling_and_non_autokill_seeking(loop_type, expected):
    manager = TweenManager()
    value, tween = value_tween(manager)
    tween.SetLoops(3, loop_type).SetAutoKill(False)
    manager.Update(1.5)
    assert value[0] == pytest.approx(expected)
    tween.Goto(0.25)
    assert value[0] == pytest.approx(2.5)
    assert not tween.IsPlaying()


def test_tuple_relative_from_and_custom_curve():
    manager, value = TweenManager(), [(2.0, 4.0)]
    tween = manager.To(lambda: value[0], lambda v: value.__setitem__(0, v), (4.0, 8.0), 1).From(relative=True).SetEase(lambda t: t)
    assert value[0] == (6, 12)
    manager.Update(0.5)
    assert value[0] == (4, 8)
    manager.Update(0.5)
    assert value[0] == (2, 4)
    assert not tween.IsActive()


def test_manual_and_unscaled_clocks_do_not_receive_normal_updates():
    manager = TweenManager()
    manual_value, manual = value_tween(manager)
    independent_value, independent = value_tween(manager)
    manual.SetUpdate(UpdateType.Manual)
    independent.SetUpdate(UpdateType.Normal, independent=True)
    manager.Update(0, 0.5)
    assert manual_value[0] == 0 and independent_value[0] == 5
    manager.ManualUpdate(0.25, 0.5)
    assert manual_value[0] == 2.5


def test_callbacks_can_create_and_kill_tweens_without_mutating_iteration():
    manager, activity = TweenManager(), []
    manager._on_activity = lambda phase, active: activity.append((phase, active))
    value, first = value_tween(manager)
    second_value, second = value_tween(manager)
    created = []
    first.OnUpdate(lambda: (second.Kill(), created.append(value_tween(manager))))
    manager.Update(0.5)
    assert value[0] == 5 and second_value[0] == 0
    assert created[0][0][0] == 0
    manager.Clear()
    assert activity[0] == (UpdateType.Normal, True)
    assert activity[-1] == (UpdateType.Normal, False)


def test_sequence_append_join_insert_nested_and_callbacks():
    manager = TweenManager()
    first_value, first = value_tween(manager)
    joined_value, joined = value_tween(manager, end=20)
    last_value, last = value_tween(manager, end=30)
    nested = manager.Sequence().Append(first).Join(joined)
    events = []
    sequence = manager.Sequence().Append(nested).AppendCallback(lambda: events.append("joined"))
    sequence.Append(last).SetAutoKill(False)
    manager.Update(0.5)
    assert (first_value[0], joined_value[0], last_value[0]) == (5, 10, 0)
    manager.Update(1)
    assert (first_value[0], joined_value[0], last_value[0]) == (10, 20, 15)
    assert events == ["joined"]
    sequence.Rewind()
    assert (first_value[0], joined_value[0], last_value[0]) == (0, 0, 0)


def test_sequence_children_receive_callbacks_once_and_repeat_each_loop():
    manager, events = TweenManager(), []
    value, child = value_tween(manager)
    child.OnStart(lambda: events.append("start")).OnComplete(lambda: events.append("end"))
    sequence = manager.Sequence().AppendCallback(lambda: events.append("zero")).Append(child)
    sequence.SetLoops(2).SetAutoKill(False)
    manager.Update(2)
    assert value[0] == 10
    assert events == ["zero", "start", "end", "zero", "end"]


def test_backwards_and_seek_restore_later_sequence_children():
    manager = TweenManager()
    value, first = value_tween(manager)
    second = manager.To(lambda: value[0], lambda v: value.__setitem__(0, v), 20., 1).SetEase(Ease.Linear)
    sequence = manager.Sequence().Append(first).Append(second).SetAutoKill(False)
    manager.Update(2)
    assert value[0] == 20
    sequence.Goto(0.5)
    assert value[0] == 5
    sequence.Goto(2).PlayBackwards()
    manager.Update(1.5)
    assert value[0] == 5


def test_sequence_rejects_duplicate_ownership_and_infinite_children():
    manager = TweenManager()
    _, child = value_tween(manager)
    first = manager.Sequence().Append(child)
    with pytest.raises(ValueError, match="exactly once"):
        manager.Sequence().Append(child)
    _, infinite = value_tween(manager)
    with pytest.raises(ValueError, match="finite"):
        first.Append(infinite.SetLoops(-1))


def test_backward_rewind_does_not_autokill():
    manager = TweenManager()
    value, tween = value_tween(manager)
    tween.SetAutoKill(False)
    manager.Update(1)
    tween.PlayBackwards()
    manager.Update(1)
    assert value[0] == 0 and tween.IsActive() and not tween.IsPlaying()


def test_relative_nested_sequence_and_sequence_ease():
    manager, value = TweenManager(), [2.0]
    tween = manager.To(lambda: value[0], lambda v: value.__setitem__(0, v), 4.0, 1).SetEase(Ease.Linear)
    nested = manager.Sequence().Append(tween)
    sequence = manager.Sequence().Append(nested).SetRelative().SetEase(lambda t: t * t)
    manager.Update(0.5)
    assert value[0] == pytest.approx(3.0)
    manager.Update(0.5)
    assert value[0] == 6.0
    with pytest.raises(ValueError, match="Tweeners"):
        manager.Sequence().SetLoops(2, LoopType.Incremental)
    from_value = [2.0]
    from_tween = manager.To(lambda: from_value[0], lambda v: from_value.__setitem__(0, v), 4.0, 1).From().SetRelative()
    from_tween.Complete()
    assert from_value[0] == 2.0
