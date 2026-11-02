"""Startup callbacks precede phase publication; update callbacks observe its result."""
import pytest

from infernux_tween import Ease, TweenManager


def make(manager, duration=1.):
    value = [0.]
    handle = manager.to(lambda: value[0], lambda x: value.__setitem__(0, x), 1., duration)
    return handle.set_ease(Ease.LINEAR).set_auto_kill(False), value


@pytest.mark.parametrize("sequenced", [False, True])
def test_initial_callbacks_read_old_phase_with_completed_delay(sequenced):
    manager, events = TweenManager(), []
    leaf, values = make(manager)
    root = manager.sequence().append(leaf).set_auto_kill(False) if sequenced else leaf
    root.set_delay(.5, False)
    def observe(name):
        events.append((name, root.position, root.completed_loops(), root.elapsed(), root.elapsed_delay()))
    root.on_start(lambda: observe("start")).on_play(lambda: observe("play")).on_update(lambda: observe("update"))
    try:
        manager.update(.25)
        assert events == []
        manager.update(.5)
        assert events == [("start", 0., 0, 0., .5), ("play", 0., 0, 0., .5), ("update", .25, 0, .25, .5)]
        assert values == [.25]
    finally:
        manager.clear()


@pytest.mark.parametrize("event", ["start", "play"])
def test_pausing_in_initial_callback_still_applies_the_captured_frame(event):
    manager, events = TweenManager(), []
    handle, values = make(manager)
    def pause():
        events.append((event, handle.position))
        handle.pause()
    getattr(handle, "on_" + event)(pause)
    handle.on_update(lambda: events.append(("update", handle.position)))
    try:
        manager.update(.25)
        assert events == [(event, 0.), ("update", .25)]
        assert values == [.25] and not handle.is_playing()
        manager.update(.25)
        assert values == [.25]
    finally:
        manager.clear()


def test_initial_completion_query_does_not_see_the_pending_final_frame():
    manager, events = TweenManager(), []
    handle, _ = make(manager)
    handle.set_loops(3)
    handle.on_start(lambda: events.append(("start", handle.completed_loops(), handle.is_complete())))
    handle.on_update(lambda: events.append(("update", handle.completed_loops(), handle.is_complete())))
    try:
        manager.update(3)
        assert events == [("start", 0, False), ("update", 3, True)]
    finally:
        manager.clear()


def test_delayed_getter_observes_consumed_delay_before_startup():
    manager, holder, observed = TweenManager(), [], []
    def read():
        observed.append(holder[0].elapsed_delay())
        return 0.
    handle = manager.to(read, lambda x: None, 1., 1.).set_delay(.5)
    holder.append(handle)
    try:
        manager.update(.25)
        manager.update(.5)
        assert observed == [.5] and handle.position == .25
    finally:
        manager.clear()


def test_killing_in_start_does_not_publish_or_apply_pending_state():
    manager, events = TweenManager(), []
    handle, values = make(manager)
    def kill():
        events.append(handle.position)
        handle.kill()
    handle.on_start(kill)
    try:
        manager.update(.25)
        assert events == [0.] and values == [0.] and not handle.is_active()
        assert handle.position == 0.
    finally:
        manager.clear()


def test_zero_duration_start_observes_previous_loop_count():
    manager, events = TweenManager(), []
    handle, _ = make(manager, 0.)
    handle.on_start(lambda: events.append(("start", handle.completed_loops(), handle.is_complete())))
    handle.on_update(lambda: events.append(("update", handle.completed_loops(), handle.is_complete())))
    try:
        manager.update(.25)
        assert events == [("start", 0, False), ("update", 1, True)]
    finally:
        manager.clear()


@pytest.mark.parametrize("event", ["start", "play"])
@pytest.mark.parametrize("sequenced", [False, True])
def test_seeking_in_initial_callback_preserves_the_pending_frame(event, sequenced):
    manager, events = TweenManager(), []
    leaf, values = make(manager)
    root = manager.sequence().append(leaf).set_auto_kill(False) if sequenced else leaf

    def seek():
        events.append((event, root.position))
        root.goto(.75)

    getattr(root, "on_" + event)(seek)
    root.on_update(lambda: events.append(("update", root.position)))
    try:
        manager.update(.25)
        assert events == [(event, 0.), ("update", .75), ("update", .25)]
        assert root.position == .25 and values == [.25]
        assert not root.is_playing()
    finally:
        manager.clear()


@pytest.mark.parametrize("duration", [.125, .5, 2.])
def test_reconfiguring_in_start_applies_the_pending_phase_to_the_new_values(duration):
    manager = TweenManager()
    handle, values = make(manager)
    handle.on_start(lambda: handle.change_end_value(2., duration))
    try:
        manager.update(.25)
        assert handle.position == min(.25, duration)
        assert values == [min(2., .5 / duration)]
        assert handle.completed_loops() == 0 and not handle.is_complete()
    finally:
        manager.clear()


def test_reconfigured_clock_continues_backwards_after_the_initial_frame():
    manager = TweenManager()
    handle, values = make(manager)

    def configure():
        handle.change_end_value(2., .5)
        handle.flip()

    handle.on_start(configure)
    try:
        manager.update(.25)
        assert handle.is_playing() and handle.position == .25 and values == [1.]
        manager.update(.125)
        assert handle.position == .125 and values == [.5]
    finally:
        manager.clear()


@pytest.mark.parametrize("duration", [0., float("inf")])
def test_other_clock_kinds_consume_delay_before_the_getter_and_capture_its_step(duration):
    manager, holder, observed = TweenManager(), [], []

    def read():
        handle = holder[0]
        observed.append(handle.elapsed_delay())
        handle.time_scale = 0.
        return 0.

    handle = manager.to(read, lambda value: None, 1., duration).set_delay(.5).set_auto_kill(False)
    holder.append(handle)
    try:
        manager.update(.25)
        assert observed == [] and not handle.played_once
        manager.update(.25)
        assert observed == [] and not handle.played_once
        manager.update(.25)
        assert observed == [.5] and handle.played_once
        assert handle.is_complete() == (duration == 0.)
        assert handle.position == (0. if duration == 0. else .25)
    finally:
        manager.clear()


@pytest.mark.parametrize("duration", [0., 1., float("inf")])
def test_frame_step_threshold_is_shared_by_all_clock_kinds(duration):
    manager, reads = TweenManager(), []
    handle = manager.to(lambda: reads.append(True) or 0., lambda value: None, 1., duration).set_auto_kill(False)
    try:
        manager.update(5e-7)
        assert reads == [] and not handle.played_once
        manager.update(1e-6)
        assert reads == [True] and handle.played_once
    finally:
        manager.clear()
