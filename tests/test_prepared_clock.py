"""Timing recipes retain their state without frame-time rebuilding."""
import pytest
from infernux_tween import Ease, LoopType, TweenManager


def test_stable_updates_reuse_the_same_native_clock_recipe():
    manager, values = TweenManager(), []
    try:
        handle = manager.to(lambda: 0., values.append, 4., 2.).set_ease(Ease.LINEAR)
        handle.force_init()
        clock = handle._sample_clock
        for _ in range(4):
            manager.update(.125)
            assert handle._sample_clock is clock
        assert values[-1] == 1.
    finally:
        manager.clear()


def test_retained_clock_is_independent_of_later_timing_configuration():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda value: None, 1., .1).set_loops(3)
        clock, endpoint = handle._sample_clock, handle.full_duration
        handle.set_delay(.5).set_loops(4, LoopType.YOYO)
        assert clock(endpoint, True, False) == (2, 1.)
        assert handle._sample_clock is not clock
        assert handle._progress_at(handle.full_duration) == (3, 0.)
    finally:
        manager.clear()


def test_orientation_flags_are_live_without_recompiling_the_clock():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda value: None, 1., 1.).set_loops(3)
        clock = handle._sample_clock
        assert handle._progress_at(1.25) == (1, .25)
        handle.loop_type = LoopType.YOYO
        assert handle._progress_at(1.25) == (1, .75)
        handle.set_inverted()
        assert handle._progress_at(1.25) == (1, .25)
        assert handle._sample_clock is clock
    finally:
        manager.clear()


@pytest.mark.parametrize('position', [-2.25, -.25, 0., .25, 1., 1.25, 2., 2.25, 3.])
def test_prepared_clock_preserves_signed_and_cycle_boundary_phases(position):
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda value: None, 1., 1.).set_loops(3, LoopType.YOYO)
        cycle, progress = handle._progress_at(position)
        expected_cycle = int(position // 1.) - int(position > 0 and position % 1. == 0)
        fraction = 1. if position > 0 and position % 1. == 0 else position % 1.
        expected_progress = 1 - fraction if expected_cycle % 2 else fraction
        assert (cycle, progress) == (expected_cycle, expected_progress)
    finally:
        manager.clear()


def test_same_timing_does_not_share_mutable_playback_state():
    manager, values = TweenManager(), [0., 0.]
    try:
        first = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), 1., 1.).set_ease(Ease.LINEAR)
        second = manager.to(lambda: values[1], lambda value: values.__setitem__(1, value), 1., 1.).set_ease(Ease.LINEAR)
        second.pause()
        manager.update(.25)
        second.goto(.75)
        assert values == [.25, .75]
        assert first.position == .25 and second.position == .75
    finally:
        manager.clear()


def test_zero_duration_sign_is_preserved_in_the_prepared_extent():
    from math import copysign
    manager = TweenManager()
    try:
        positive = manager.to(lambda: 0., lambda value: None, 1., 0.)
        negative = manager.to(lambda: 0., lambda value: None, 1., -0.)
        assert copysign(1., positive.duration()) == 1.
        assert copysign(1., negative.duration()) == -1.
    finally:
        manager.clear()
