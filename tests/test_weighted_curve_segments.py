"""Weighted segments preserve their inverse branch and shared curve state."""
import math
import threading

import numpy as np
import pytest

from infernux import AnimationCurve, Keyframe, WeightedMode
from infernux_tween import EaseCurve


def weighted_curve(first_weight, last_weight, first_slope=0., last_slope=0.):
    first = Keyframe(0, 0, 0, first_slope)
    first.out_weight, first.weighted_mode = first_weight, WeightedMode.OUT
    last = Keyframe(1, 1, last_slope, 0)
    last.in_weight, last.weighted_mode = last_weight, WeightedMode.IN
    return AnimationCurve(first, last)


def smoothstep(time):
    return time * time * (3 - 2 * time)


@pytest.mark.parametrize('time', [.1, .25, .5, .75, .9])
def test_linear_horizontal_handles_retain_smoothstep_values(time):
    curve = weighted_curve(1 / 3, 1 / 3)
    assert curve.evaluate(time) == pytest.approx(smoothstep(time), abs=1e-6, rel=0)


@pytest.mark.parametrize('time', [.1, .25, .5, .75, .9])
def test_quadratic_horizontal_handles_select_the_inside_root(time):
    curve = weighted_curve(.25, 5 / 12)
    parameter = (math.sqrt(.75 ** 2 + time) - .75) / .5
    assert curve.evaluate(time) == pytest.approx(smoothstep(parameter), abs=2e-6, rel=0)


def test_nonmonotonic_time_handles_select_the_first_admissible_cubic_root():
    curve = weighted_curve(2, 2, 3, 3)
    parameter = .5 + math.sqrt(.15)
    remaining = 1 - parameter
    expected = 3 * remaining ** 2 * parameter * 6 - 3 * remaining * parameter ** 2 * 5 + parameter ** 3
    assert curve.evaluate(.5) == pytest.approx(expected, abs=2e-6, rel=0)


def test_weight_edits_invalidate_new_samples_without_mutating_a_retained_snapshot():
    curve = weighted_curve(.9, .01, 4., -2.)
    ease = EaseCurve(curve)
    times = np.linspace(0, 1, 129, dtype=np.float64)
    frozen = curve._native_snapshot()
    before = np.asarray(frozen.evaluate_many(times))
    assert np.array_equal(np.asarray(ease.evaluate_many(times)), before)
    key = curve[0]
    key.out_weight = .1
    curve.move_key(0, key)
    scalar = np.asarray([curve.evaluate(time) for time in times], dtype=np.float64)
    batch = np.asarray(curve.evaluate_many(times))
    output = np.empty_like(times)
    curve.evaluate_into(times, output)
    assert np.array_equal(scalar, batch)
    assert np.array_equal(output, batch)
    assert np.array_equal(np.asarray(ease.evaluate_many(times)), batch)
    assert np.array_equal(np.asarray(frozen.evaluate_many(times)), before)
    assert not np.array_equal(before, batch)
    assert curve.evaluate(-1) == 0
    assert curve.evaluate(1) == 1


@pytest.mark.parametrize('duration', [None, 2.7])
def test_weighted_bulk_sampling_releases_the_gil(duration):
    curve = weighted_curve(.75, .15, 4., -2.)
    times = np.linspace(0, 1, 256000, dtype=np.float64)
    output = np.empty_like(times)
    curve._native_snapshot()
    started, stopped = threading.Event(), threading.Event()
    observed = [0]

    def worker():
        started.set()
        while not stopped.is_set():
            observed[0] += 1

    thread = threading.Thread(target=worker)
    thread.start()
    started.wait()
    try:
        before = observed[0]
        if duration is None:
            curve.evaluate_into(times, output)
        else:
            EaseCurve(curve).evaluate_into(times, output, duration)
        assert observed[0] > before + 100
        assert np.all(np.isfinite(output))
    finally:
        stopped.set()
        thread.join(timeout=5)
