"""Long-running loops advance a bounded phase instead of a growing float clock."""
import pytest

from infernux_tween import Ease, LoopType, TweenManager


def scalar(manager, duration=1.):
    values = [0.]
    handle = manager.to(lambda: values[0], lambda x: values.__setitem__(0, x), 1., duration)
    handle.set_ease(Ease.LINEAR).set_auto_kill(False)
    return handle, values


def test_large_loop_count_keeps_frame_progress_and_backwards_boundary():
    manager = TweenManager()
    handle, values = scalar(manager)
    try:
        handle.set_loops(-1).goto(262144., True)
        manager.update(1 / 64)
        assert handle.completed_loops() == 262144
        assert handle.position == 1 / 64 and values == [1 / 64]
        handle.play_backwards()
        manager.update(1 / 64)
        assert handle.position == 1. and handle.completed_loops() == 262144
    finally:
        manager.clear()


def test_fractional_loop_duration_keeps_local_single_precision_across_frames():
    manager = TweenManager()
    handle, _ = scalar(manager, .1)
    try:
        handle.set_loops(-1)
        for _ in range(12):
            manager.update(1 / 64)
        assert handle.position == 0.08749999850988388
        assert handle.completed_loops() == 1
    finally:
        manager.clear()


@pytest.mark.parametrize("mode", [LoopType.RESTART, LoopType.YOYO, LoopType.INCREMENTAL])
def test_large_sequence_keeps_child_phase_and_loop_callbacks(mode):
    manager, events = TweenManager(), []
    child, values = scalar(manager)
    root = manager.sequence().append(child).set_loops(-1, mode).set_auto_kill(False)
    root.on_step_complete(lambda: events.append(root.completed_loops()))
    try:
        root.goto(262144., True)
        manager.update(.25)
        assert root.position == .25 and root.completed_loops() == 262144
        expected = 262144.25 if mode is LoopType.INCREMENTAL else .25
        assert values == [expected]
        assert events == []
        manager.update(.75)
        assert events == [262145]
    finally:
        manager.clear()


def test_finite_completion_and_reverse_reuse_native_state():
    manager, events = TweenManager(), []
    handle, values = scalar(manager)
    handle.set_loops(3).on_complete(lambda: events.append("complete"))
    try:
        clock = handle._phase_clock
        manager.update(3.25)
        assert handle._phase_clock is clock
        assert handle.completed_loops() == 3 and handle.position == 1. and handle.is_complete()
        assert values == [1.] and events == ["complete"]
        handle.play_backwards()
        manager.update(.25)
        assert handle.position == .75 and handle.completed_loops() == 2
        assert not handle.is_complete() and values == [.75]
    finally:
        manager.clear()


def test_delay_endpoint_waits_until_a_positive_playback_step():
    manager, events = TweenManager(), []
    handle, values = scalar(manager)
    handle.set_delay(.5).on_start(lambda: events.append("start"))
    try:
        manager.update(.5)
        assert handle.elapsed_delay() == .5 and handle.position == 0
        assert not handle.played_once and events == []
        manager.update(.25)
        assert handle.position == .25 and values == [.25] and events == ["start"]
    finally:
        manager.clear()


def test_reentrant_seek_replaces_the_state_used_by_the_next_frame():
    manager, events = TweenManager(), []
    handle, values = scalar(manager)
    handle.set_loops(-1)
    def seek_once():
        if not events:
            events.append("seek")
            handle.goto(262144., True)
    handle.on_update(seek_once)
    try:
        manager.update(.25)
        manager.update(.25)
        assert handle.completed_loops() == 262144 and handle.position == .25
        assert values == [.25]
    finally:
        manager.clear()
