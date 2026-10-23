import pytest

from infernux_tween import Ease, LoopType, TweenManager, UpdateType


def value_tween(manager, end=10.0, duration=1.0):
    value = [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), end, duration).set_ease(Ease.LINEAR)
    return value, tween


@pytest.mark.parametrize("ease", list(Ease))
def test_easing_curves_have_exact_endpoints_and_finite_samples(ease):
    from math import isfinite
    from infernux_tween.ease import resolve_ease

    curve = resolve_ease(ease, 3) if ease.value.endswith("Flash") else resolve_ease(ease)
    assert curve(0) == pytest.approx(0)
    assert curve(1) == pytest.approx(1)
    assert all(isfinite(curve(i / 100)) for i in range(101))


def test_delay_capture_pause_restart_and_completion_callbacks():
    manager, events = TweenManager(), []
    value, tween = value_tween(manager)
    tween.set_delay(0.5).set_auto_kill(False).on_start(lambda: events.append("start"))
    tween.on_step_complete(lambda: events.append("step")).on_complete(lambda: events.append("complete"))
    manager.update(0.25)
    value[0] = 2.0
    manager.update(0.75)
    assert value[0] == pytest.approx(6)
    tween.pause()
    manager.update(4)
    assert value[0] == pytest.approx(6)
    tween.play()
    manager.update(0.5)
    assert value[0] == 10
    assert events == ["start", "step", "complete"]
    tween.restart(include_delay=False)
    assert value[0] == 2
    manager.update(1)
    assert events == ["start", "step", "complete", "step", "complete"]


@pytest.mark.parametrize("loop_type, expected", [(LoopType.RESTART, 5), (LoopType.YOYO, 5), (LoopType.INCREMENTAL, 15)])
def test_loop_sampling_and_non_autokill_seeking(loop_type, expected):
    manager = TweenManager()
    value, tween = value_tween(manager)
    tween.set_loops(3, loop_type).set_auto_kill(False)
    manager.update(1.5)
    assert value[0] == pytest.approx(expected)
    tween.goto(0.25)
    assert value[0] == pytest.approx(2.5)
    assert not tween.is_playing()


def test_tuple_relative_from_and_custom_curve():
    manager, value = TweenManager(), [(2.0, 4.0)]
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), (4.0, 8.0), 1).from_(is_relative=True).set_ease(lambda t, d, a, p: t/d)
    assert value[0] == (6, 12)
    manager.update(0.5)
    assert value[0] == (4, 8)
    manager.update(0.5)
    assert value[0] == (2, 4)
    assert not tween.is_active()


def test_manual_and_unscaled_clocks_do_not_receive_normal_updates():
    manager = TweenManager()
    manual_value, manual = value_tween(manager)
    independent_value, independent = value_tween(manager)
    manual.set_update(UpdateType.MANUAL)
    independent.set_update(UpdateType.NORMAL, is_independent_update=True)
    manager.update(0, 0.5)
    assert manual_value[0] == 0 and independent_value[0] == 5
    manager.manual_update(0.25, 0.5)
    assert manual_value[0] == 2.5


def test_callbacks_can_create_and_kill_tweens_without_mutating_iteration():
    manager, activity = TweenManager(), []
    manager._on_activity = lambda phase, active: activity.append((phase, active))
    value, first = value_tween(manager)
    second_value, second = value_tween(manager)
    created = []
    first.on_update(lambda: (second.kill(), created.append(value_tween(manager))))
    manager.update(0.5)
    assert value[0] == 5 and second_value[0] == 0
    assert created[0][0][0] == 0
    manager.clear()
    assert activity[0] == (UpdateType.NORMAL, True)
    assert activity[-1] == (UpdateType.NORMAL, False)


def test_sequence_append_join_insert_nested_and_callbacks():
    manager = TweenManager()
    first_value, first = value_tween(manager)
    joined_value, joined = value_tween(manager, end=20)
    last_value, last = value_tween(manager, end=30)
    nested = manager.sequence().append(first).join(joined)
    events = []
    sequence = manager.sequence().append(nested).append_callback(lambda: events.append("joined"))
    sequence.append(last).set_auto_kill(False)
    manager.update(0.5)
    assert (first_value[0], joined_value[0], last_value[0]) == (5, 10, 0)
    manager.update(1)
    assert (first_value[0], joined_value[0], last_value[0]) == (10, 20, 15)
    assert events == ["joined"]
    sequence.rewind()
    assert (first_value[0], joined_value[0], last_value[0]) == (0, 0, 0)


def test_sequence_children_receive_callbacks_once_and_repeat_each_loop():
    manager, events = TweenManager(), []
    value, child = value_tween(manager)
    child.on_start(lambda: events.append("start")).on_complete(lambda: events.append("end"))
    sequence = manager.sequence().append_callback(lambda: events.append("zero")).append(child)
    sequence.set_loops(2).set_auto_kill(False)
    manager.update(2)
    assert value[0] == 10
    assert events == ["zero", "start", "end", "zero", "end"]


def test_backwards_and_seek_restore_later_sequence_children():
    manager = TweenManager()
    value, first = value_tween(manager)
    second = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 20., 1).set_ease(Ease.LINEAR)
    sequence = manager.sequence().append(first).append(second).set_auto_kill(False)
    manager.update(2)
    assert value[0] == 20
    sequence.goto(0.5)
    assert value[0] == 5
    sequence.goto(2).play_backwards()
    manager.update(1.5)
    assert value[0] == 5


def test_sequence_rejects_duplicate_ownership_and_normalizes_infinite_children():
    manager = TweenManager()
    _, child = value_tween(manager)
    first = manager.sequence().append(child)
    with pytest.raises(ValueError, match="exactly once"):
        manager.sequence().append(child)
    _, infinite = value_tween(manager)
    first.append(infinite.set_loops(-1))
    assert infinite.loops() == 1 and first.duration() == 2


def test_inverted_sequence_pauses_on_its_reverse_timeline_and_resumes_without_losing_time():
    manager, value, events = TweenManager(), [0.0], []
    child = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1).set_ease(Ease.LINEAR)
    root = manager.sequence().append(child).set_inverted().set_auto_kill(False)
    root.insert_callback(0.25, lambda: (events.append(root.elapsed()), root.pause()))
    manager.update(0.5)
    assert value[0] == 5 and events == []
    manager.update(0.5)
    assert root.is_active() and not root.is_playing() and root.elapsed() == 0.75
    assert value[0] == 2.5 and events == [0.75]
    root.play()
    manager.update(0.25)
    assert value[0] == 0 and root.is_complete() and events == [0.75]


def test_backward_rewind_does_not_autokill():
    manager = TweenManager()
    value, tween = value_tween(manager)
    tween.set_auto_kill(False)
    manager.update(1)
    tween.play_backwards()
    manager.update(1)
    assert value[0] == 0 and tween.is_active() and not tween.is_playing()


def test_relative_nested_sequence_and_sequence_ease():
    manager, value = TweenManager(), [2.0]
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 4.0, 1).set_ease(Ease.LINEAR)
    nested = manager.sequence().append(tween)
    sequence = manager.sequence().append(nested).set_relative().set_ease(lambda t, d, a, p: (t/d)**2)
    manager.update(0.5)
    assert value[0] == pytest.approx(3.0)
    manager.update(0.5)
    assert value[0] == 6.0
    continued = manager.sequence().append(manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 4.0, 1).set_ease(Ease.LINEAR))
    continued.set_relative().set_loops(2, LoopType.INCREMENTAL)
    manager.update(1.5)
    assert value[0] == 12
    from_value = [2.0]
    from_tween = manager.to(lambda: from_value[0], lambda v: from_value.__setitem__(0, v), 4.0, 1).from_().set_relative()
    from_tween.complete()
    assert from_value[0] == 2.0


@pytest.mark.parametrize("backwards,yoyo,nested", (
    (False, False, False), (True, False, False), (False, True, False),
    (False, False, True), (True, False, True), (False, True, True),
))
def test_sequence_callbacks_follow_playback_direction_instead_of_ease_rebounds(backwards, yoyo, nested):
    manager, events = TweenManager(), []
    _, child = value_tween(manager, end=1.0)
    body = manager.sequence().append(child).insert_callback(0.95, lambda: events.append(body.elapsed()))
    body.set_ease(Ease.OUT_BOUNCE)
    root = manager.sequence().append(body) if nested else body
    root.set_auto_kill(False).set_loops(2 if yoyo else 1, LoopType.YOYO)
    if backwards:
        root.goto(root.duration()).play_backwards()
    for _ in range(240 if yoyo else 120):
        manager.update(1 / 120)
    assert len(events) == (6 if yoyo else 3)
    manager.clear()


def test_nested_sequence_callbacks_follow_the_clock_supplied_by_the_parent():
    manager, events = TweenManager(), []
    _, child = value_tween(manager, end=1.0)
    body = manager.sequence().append(child).insert_callback(0.95, lambda: events.append(body.elapsed()))
    manager.sequence().append(body).set_ease(Ease.OUT_BOUNCE)
    for _ in range(120):
        manager.update(1 / 120)
    assert len(events) == 5
    manager.clear()


def test_delay_play_and_seek_use_elapsed_time_without_repeating_callbacks():
    manager, events = TweenManager(), []
    value, tween = value_tween(manager)
    tween.set_delay(1).set_auto_kill(False)
    tween.on_start(lambda: events.append("start")).on_play(lambda: events.append("play"))
    tween.on_rewind(lambda: events.append("rewind"))
    tween.pause().play()
    manager.update(0.5)
    assert events == [] and value[0] == 0
    manager.update(0.5)
    assert events == ["start", "play"]
    tween.goto(0.5)
    assert tween.elapsed() == 0.5 and value[0] == 5
    tween.rewind(False).rewind(False)
    assert events == ["start", "play", "rewind"] and value[0] == 0
    tween.restart()
    manager.update(0.5)
    assert events == ["start", "play", "rewind"]
    manager.update(0.5)
    assert events == ["start", "play", "rewind", "play"]
    tween.goto(tween.duration())
    assert tween.is_complete() and value[0] == 10
    tween.restart(False)
    manager.update(0.25)
    assert value[0] == 2.5


def test_sequence_child_delay_keeps_the_getter_live_until_its_actual_start():
    manager, value, writes = TweenManager(), [5.0], []
    def write(item):
        value[0] = item
        writes.append(item)
    child = manager.to(lambda: value[0], write, 10.0, 1).set_delay(1).set_ease(Ease.LINEAR)
    manager.sequence().append(child)
    manager.update(0.5)
    assert not writes
    value[0] = 7.0
    manager.update(0.5)
    assert value[0] == 7.0
    manager.update(0.5)
    assert value[0] == 8.5


def test_sequence_delay_is_a_repeated_interval_unless_explicitly_one_time():
    manager = TweenManager()
    value, child = value_tween(manager)
    sequence = manager.sequence().append(child).set_delay(1).set_loops(2).set_auto_kill(False)
    assert sequence.duration() == 4
    manager.update(1.5)
    assert value[0] == 5
    manager.update(1)
    assert value[0] == 0 and not sequence.is_complete()
    manager.update(1)
    assert value[0] == 5
    manager.update(0.5)
    assert value[0] == 10 and sequence.is_complete()
    _, child = value_tween(manager)
    once = manager.sequence().append(child).set_delay(1, False).set_loops(2)
    assert once.duration() == 2 and once.full_duration == 3


@pytest.mark.parametrize("ease,auto_kill,nested,loops,delta,child_callback", (
    (Ease.LINEAR, True, False, 1, 2, False),
    (Ease.LINEAR, False, False, 1, 2, False),
    (Ease.LINEAR, True, False, 3, 5, False),
    (Ease.OUT_QUAD, True, False, 1, 2, False),
    (Ease.OUT_SINE, True, False, 1, 2, False),
    (Ease.LINEAR, True, True, 1, 3, False),
    (Ease.OUT_QUAD, True, True, 1, 3, False),
    (Ease.LINEAR, True, True, 1, 3, True),
))
def test_sequence_callback_pause_stops_later_children_and_callbacks_in_that_update(
        ease, auto_kill, nested, loops, delta, child_callback):
    from math import asin, pi, sin, sqrt
    manager, events = TweenManager(), []
    first_value, first = value_tween(manager)
    value, second = value_tween(manager)
    sequence = manager.sequence()
    body = manager.sequence() if nested else sequence
    body.append(first)
    if child_callback:
        first.on_complete(sequence.pause)
    else:
        body.append_callback(sequence.pause)
    body.append(second).append_callback(lambda: events.append("later"))
    if nested:
        sequence.append_interval(0.5).append(body)
    joined_value = None
    if not nested:
        joined_value = [0.0]
        joined = manager.to(lambda: joined_value[0], lambda value: joined_value.__setitem__(0, value), 10.0, 2)
        sequence.insert(0, joined.set_ease(Ease.LINEAR))
    sequence.set_auto_kill(auto_kill).set_loops(loops).set_ease(ease)
    duration, boundary = sequence.duration(False), 1.5 if nested else 1.0
    expected = (boundary if ease == Ease.LINEAR else duration * 2 / pi * asin(boundary / duration)
                if ease == Ease.OUT_SINE else duration * (1 - sqrt(1 - boundary / duration)))
    manager.update(delta)
    assert sequence.is_active() and not sequence.is_playing()
    assert sequence.elapsed() == pytest.approx(expected, abs=1e-8)
    assert first_value[0] == 10 and value[0] == 0 and not events
    if joined_value is not None:
        assert joined_value[0] == pytest.approx(10 * boundary / duration)
    sequence.play()
    manager.update(0.25)
    assert sequence.elapsed() == pytest.approx(expected + 0.25, abs=1e-8)
    progress = (expected + 0.25) / duration
    sample = duration * (progress if ease == Ease.LINEAR else sin(progress * pi / 2)
                         if ease == Ease.OUT_SINE else 1 - (1 - progress)**2)
    assert value[0] == pytest.approx(10 * (sample - boundary), abs=1e-7)
    assert not events and sequence.is_playing()
    if joined_value is not None:
        assert joined_value[0] == pytest.approx(10 * sample / duration, abs=1e-7)
    if not nested and ease == Ease.LINEAR and loops == 1:
        sequence.goto(2).play_backwards()
        manager.update(1.5)
        assert sequence.is_active() and not sequence.is_playing() and sequence.elapsed() == 1
        assert first_value[0] == 10 and value[0] == 0 and joined_value[0] == 5
        sequence.play()
        manager.update(0.25)
        assert sequence.elapsed() == 0.75 and first_value[0] == 7.5
        assert value[0] == 0 and joined_value[0] == 3.75


def test_joined_child_lifecycle_pause_samples_other_children_only_to_that_boundary():
    for event, boundary in (("start", 0.5), ("step", 0.5), ("complete", 1.0)):
        manager, joined_value = TweenManager(), [0.0]
        joined = manager.to(lambda: joined_value[0], lambda value: joined_value.__setitem__(0, value), 10.0, 2)
        sequence = manager.sequence().append(joined.set_ease(Ease.LINEAR))
        short = manager.to(lambda: 0.0, lambda value: None, 1.0, 0.5 if event == "step" else 1)
        if event == "start":
            short.set_delay(0.5).on_start(sequence.pause)
        elif event == "step":
            short.set_loops(2).on_step_complete(sequence.pause)
        else:
            short.on_complete(sequence.pause)
        sequence.insert(0, short)
        manager.update(2)
        assert sequence.is_active() and not sequence.is_playing() and sequence.elapsed() == boundary
        assert joined_value[0] == 5 * boundary
        sequence.play()
        manager.update(0.25)
        assert sequence.is_active() and sequence.is_playing() and sequence.elapsed() == boundary + 0.25
        assert joined_value[0] == 5 * (boundary + 0.25)
