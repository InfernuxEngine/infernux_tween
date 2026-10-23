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


def test_delay_play_and_seek_use_elapsed_time_without_repeating_callbacks():
    manager, events = TweenManager(), []
    value, tween = value_tween(manager)
    tween.SetDelay(1).SetAutoKill(False)
    tween.OnStart(lambda: events.append("start")).OnPlay(lambda: events.append("play"))
    tween.OnRewind(lambda: events.append("rewind"))
    tween.Pause().Play()
    manager.Update(0.5)
    assert events == [] and value[0] == 0
    manager.Update(0.5)
    assert events == ["start", "play"]
    tween.Goto(0.5)
    assert tween.Elapsed() == 0.5 and value[0] == 5
    tween.Rewind(False).Rewind(False)
    assert events == ["start", "play", "rewind"] and value[0] == 0
    tween.Restart()
    manager.Update(0.5)
    assert events == ["start", "play", "rewind"]
    manager.Update(0.5)
    assert events == ["start", "play", "rewind", "play"]
    tween.Goto(tween.Duration())
    assert tween.IsComplete() and value[0] == 10
    tween.Restart(False)
    manager.Update(0.25)
    assert value[0] == 2.5


def test_sequence_child_delay_keeps_the_getter_live_until_its_actual_start():
    manager, value, writes = TweenManager(), [5.0], []
    def write(item):
        value[0] = item
        writes.append(item)
    child = manager.To(lambda: value[0], write, 10.0, 1).SetDelay(1).SetEase(Ease.Linear)
    manager.Sequence().Append(child)
    manager.Update(0.5)
    assert not writes
    value[0] = 7.0
    manager.Update(0.5)
    assert value[0] == 7.0
    manager.Update(0.5)
    assert value[0] == 8.5


def test_sequence_delay_is_a_repeated_interval_unless_explicitly_one_time():
    manager = TweenManager()
    value, child = value_tween(manager)
    sequence = manager.Sequence().Append(child).SetDelay(1).SetLoops(2).SetAutoKill(False)
    assert sequence.Duration() == 4
    manager.Update(1.5)
    assert value[0] == 5
    manager.Update(1)
    assert value[0] == 0 and not sequence.IsComplete()
    manager.Update(1)
    assert value[0] == 5
    manager.Update(0.5)
    assert value[0] == 10 and sequence.IsComplete()
    _, child = value_tween(manager)
    once = manager.Sequence().Append(child).SetDelay(1, False).SetLoops(2)
    assert once.Duration() == 2 and once.full_duration == 3


@pytest.mark.parametrize("ease,auto_kill,nested,loops,delta,child_callback", (
    (Ease.Linear, True, False, 1, 2, False),
    (Ease.Linear, False, False, 1, 2, False),
    (Ease.Linear, True, False, 3, 5, False),
    (Ease.OutQuad, True, False, 1, 2, False),
    (Ease.OutSine, True, False, 1, 2, False),
    (Ease.Linear, True, True, 1, 3, False),
    (Ease.OutQuad, True, True, 1, 3, False),
    (Ease.Linear, True, True, 1, 3, True),
))
def test_sequence_callback_pause_stops_later_children_and_callbacks_in_that_update(
        ease, auto_kill, nested, loops, delta, child_callback):
    from math import asin, pi, sin, sqrt
    manager, events = TweenManager(), []
    first_value, first = value_tween(manager)
    value, second = value_tween(manager)
    sequence = manager.Sequence()
    body = manager.Sequence() if nested else sequence
    body.Append(first)
    if child_callback:
        first.OnComplete(sequence.Pause)
    else:
        body.AppendCallback(sequence.Pause)
    body.Append(second).AppendCallback(lambda: events.append("later"))
    if nested:
        sequence.AppendInterval(0.5).Append(body)
    joined_value = None
    if not nested:
        joined_value = [0.0]
        joined = manager.To(lambda: joined_value[0], lambda value: joined_value.__setitem__(0, value), 10.0, 2)
        sequence.Insert(0, joined.SetEase(Ease.Linear))
    sequence.SetAutoKill(auto_kill).SetLoops(loops).SetEase(ease)
    duration, boundary = sequence.Duration(False), 1.5 if nested else 1.0
    expected = (boundary if ease == Ease.Linear else duration * 2 / pi * asin(boundary / duration)
                if ease == Ease.OutSine else duration * (1 - sqrt(1 - boundary / duration)))
    manager.Update(delta)
    assert sequence.IsActive() and not sequence.IsPlaying()
    assert sequence.Elapsed() == pytest.approx(expected, abs=1e-8)
    assert first_value[0] == 10 and value[0] == 0 and not events
    if joined_value is not None:
        assert joined_value[0] == pytest.approx(10 * boundary / duration)
    sequence.Play()
    manager.Update(0.25)
    assert sequence.Elapsed() == pytest.approx(expected + 0.25, abs=1e-8)
    progress = (expected + 0.25) / duration
    sample = duration * (progress if ease == Ease.Linear else sin(progress * pi / 2)
                         if ease == Ease.OutSine else 1 - (1 - progress)**2)
    assert value[0] == pytest.approx(10 * (sample - boundary), abs=1e-7)
    assert not events and sequence.IsPlaying()
    if joined_value is not None:
        assert joined_value[0] == pytest.approx(10 * sample / duration, abs=1e-7)
    if not nested and ease == Ease.Linear and loops == 1:
        sequence.Goto(2).PlayBackwards()
        manager.Update(1.5)
        assert sequence.IsActive() and not sequence.IsPlaying() and sequence.Elapsed() == 1
        assert first_value[0] == 10 and value[0] == 0 and joined_value[0] == 5
        sequence.Play()
        manager.Update(0.25)
        assert sequence.Elapsed() == 0.75 and first_value[0] == 7.5
        assert value[0] == 0 and joined_value[0] == 3.75


def test_joined_child_lifecycle_pause_samples_other_children_only_to_that_boundary():
    for event, boundary in (("start", 0.5), ("step", 0.5), ("complete", 1.0)):
        manager, joined_value = TweenManager(), [0.0]
        joined = manager.To(lambda: joined_value[0], lambda value: joined_value.__setitem__(0, value), 10.0, 2)
        sequence = manager.Sequence().Append(joined.SetEase(Ease.Linear))
        short = manager.To(lambda: 0.0, lambda value: None, 1.0, 0.5 if event == "step" else 1)
        if event == "start":
            short.SetDelay(0.5).OnStart(sequence.Pause)
        elif event == "step":
            short.SetLoops(2).OnStepComplete(sequence.Pause)
        else:
            short.OnComplete(sequence.Pause)
        sequence.Insert(0, short)
        manager.Update(2)
        assert sequence.IsActive() and not sequence.IsPlaying() and sequence.Elapsed() == boundary
        assert joined_value[0] == 5 * boundary
        sequence.Play()
        manager.Update(0.25)
        assert sequence.IsActive() and sequence.IsPlaying() and sequence.Elapsed() == boundary + 0.25
        assert joined_value[0] == 5 * (boundary + 0.25)
