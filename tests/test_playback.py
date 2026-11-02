import pytest

from infernux_tween import Ease, LoopType, TweenManager, UpdateType


def value_tween(manager, end=10.0, duration=1.0):
    value = [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), end, duration).set_ease(Ease.LINEAR)
    return value, tween


@pytest.mark.parametrize("ease", [ease for ease in Ease if ease.value < 36])
def test_easing_curves_have_exact_endpoints_and_finite_samples(ease):
    from math import isfinite
    from infernux_tween.ease import resolve_ease

    curve = resolve_ease(ease, 3) if ease.label.endswith("Flash") else resolve_ease(ease)
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


@pytest.mark.parametrize('phase', list(UpdateType))
def test_tween_created_in_callback_waits_for_next_update_and_does_not_reuse_a_pending_kill(phase):
    manager = TweenManager()
    _, first = value_tween(manager)
    _, second = value_tween(manager)
    first.set_update(phase)
    second.set_update(phase).set_recyclable(True)
    manager.update(.1, update_type=phase)
    manager.update(.1, update_type=phase)
    created = []
    def replace():
        first.on_update(None)
        second.kill()
        pair = value_tween(manager)
        pair[1].set_update(phase)
        created.append(pair)
    first.on_update(replace)
    manager.update(.1, update_type=phase)
    value, replacement = created[0]
    assert replacement is not second and not second.is_active()
    assert manager.total_pooled_tweens() == 1
    assert value[0] == 0
    manager.update(.25, update_type=phase)
    assert value[0] == pytest.approx(2.5)
    replacement.pause()
    manager.update(.25, update_type=phase)
    assert value[0] == pytest.approx(2.5)
    replacement.play()
    manager.update(.25, update_type=phase)
    assert value[0] == pytest.approx(5)
    manager.clear()


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


def test_multicycle_completion_keeps_timeline_callbacks_without_recompleting_the_child():
    manager, events = TweenManager(), []
    value, child = value_tween(manager)
    child.on_start(lambda: events.append("start")).on_complete(lambda: events.append("end"))
    sequence = manager.sequence().append_callback(lambda: events.append("zero")).append(child)
    sequence.set_loops(2).set_auto_kill(False)
    manager.update(2)
    assert value[0] == 10
    assert events == ["zero", "start", "end", "zero"]


def test_backwards_and_seek_restore_later_sequence_children():
    manager = TweenManager()
    value, first = value_tween(manager)
    second = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 20., 1).set_ease(Ease.LINEAR)
    sequence = manager.sequence().append(first).append(second).set_auto_kill(False)
    manager.update(2)
    assert value[0] == 20
    sequence.goto(0.5)
    assert value[0] == 5
    sequence.goto(2)
    sequence.play_backwards()
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
    assert infinite.loops() == 2**31 - 1 and first.duration() == 2**31


def test_inverted_sequence_completion_keeps_actual_clock_despite_timeline_pause():
    manager, value, events = TweenManager(), [0.0], []
    child = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1).set_ease(Ease.LINEAR)
    root = manager.sequence().append(child).set_inverted().set_auto_kill(False)
    root.insert_callback(0.25, lambda: (events.append(root.elapsed()), root.pause()))
    manager.update(0.5)
    assert value[0] == 5 and events == []
    manager.update(0.5)
    assert root.is_active() and not root.is_playing() and root.elapsed() == 1
    assert value[0] == 0 and events == [1] and root.is_complete()
    root.play()
    manager.update(0.25)
    assert value[0] == 0 and root.is_complete() and events == [1]


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
        root.goto(root.duration())
        root.play_backwards()
    for _ in range(240 if yoyo else 120):
        manager.update(1 / 120)
    # A sequence reverses its eased clock; a nested Bounce child retains its
    # own clock. Actual Play measurements live in LoopBoundaryReference.cs.
    expected = (6 if nested else 4) if yoyo else 3
    assert len(events) == expected
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
    assert events == [] and value[0] == 0
    manager.update(0.25)
    assert events == ["start", "play"]
    tween.goto(0.5)
    assert tween.elapsed() == 0.5 and value[0] == 5
    tween.rewind(False)
    tween.rewind(False)
    assert events == ["start", "play", "rewind"] and value[0] == 0
    tween.restart()
    manager.update(0.5)
    assert events == ["start", "play", "rewind"]
    manager.update(0.5)
    assert events == ["start", "play", "rewind"]
    manager.update(0.25)
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


def test_sequence_timeline_pause_keeps_earlier_writes_and_skips_later_entries():
    # Completion, nesting, nonlinear ease and multiloop cases are covered by the
    # real SequenceDispatchReference fixture rather than inferred boundary times.
    manager, events = TweenManager(), []
    first_value, first = value_tween(manager)
    value, second = value_tween(manager)
    sequence = manager.sequence().append(first).set_auto_kill(False)
    sequence.append_callback(lambda: (events.append(sequence.elapsed()), sequence.pause()))
    sequence.append(second).append_callback(lambda: events.append("later"))
    joined_value, joined = value_tween(manager, duration=2)
    sequence.insert(0, joined)
    manager.update(1.25)
    assert sequence.is_active() and not sequence.is_playing()
    assert sequence.elapsed() == 1.25 and events == [1.25]
    assert first_value[0] == 10 and value[0] == 0 and joined_value[0] == 6.25
    sequence.play()
    manager.update(0.25)
    assert sequence.elapsed() == 1.5 and sequence.is_playing() and events == [1.25]
    assert value[0] == 5 and joined_value[0] == 7.5


def test_on_update_can_install_step_listener_for_the_same_crossing():
    for duration in (0, .25):
        manager = TweenManager()
        events = []
        tween = manager.to(lambda: 0., lambda value: None, 1., duration).set_loops(3)
        tween.on_update(lambda: tween.on_step_complete(lambda: events.append("step")))
        manager.update(1)
        assert events == ["step"] * 3
        manager.clear()


def test_joined_child_lifecycle_pause_keeps_the_actual_frame_clock():
    # SequenceInterruptReference measures these three cases at delta=1.25:
    # the earlier joined tween has already sampled 6.25 when its sibling pauses.
    for event in ("start", "step", "complete"):
        manager, joined_value = TweenManager(), [0.0]
        joined = manager.to(lambda: joined_value[0], lambda value: joined_value.__setitem__(0, value), 10.0, 2)
        sequence = manager.sequence().append(joined.set_ease(Ease.LINEAR)).set_auto_kill(False)
        short = manager.to(lambda: 0.0, lambda value: None, 1.0, 0.5 if event == "step" else 1)
        if event == "start":
            short.set_delay(0.5).on_start(sequence.pause)
        elif event == "step":
            short.set_loops(2).on_step_complete(sequence.pause)
        else:
            short.on_complete(sequence.pause)
        sequence.insert(0, short)
        manager.update(1.25)
        assert sequence.is_active() and not sequence.is_playing() and sequence.elapsed() == 1.25
        assert joined_value[0] == 6.25
        sequence.play()
        manager.update(0.25)
        assert sequence.is_active() and sequence.is_playing() and sequence.elapsed() == 1.5
        assert joined_value[0] == 7.5
