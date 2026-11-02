"""Discrete clocks retain single-precision, signed-remainder semantics."""
import gc
import math
import weakref

import pytest

from infernux_tween import Ease, EaseFactory, EaseManager


@pytest.mark.parametrize(("fps", "time", "duration", "expected"), [
    (4, -.49, 1., -.25),
    (4, 1.5, 1., 1.5),
    (4, -.49, 0., -.25),
    (4, .49, 0., .49000000953674316),
    (24, .5, 1., .4583333432674408),
    (3, 1., 2., .6666666865348816),
    (0, .49, 1., 0.),
    (-4, .49, 1., .25),
])
def test_discrete_clock_uses_signed_remainder_and_forwards_elapsed_time(fps, time, duration, expected):
    sample = EaseFactory.stop_motion(fps, custom_ease=lambda t, d, a, p: t)
    assert sample(time, duration, 1., 0.) == expected


def test_custom_clock_converts_delegate_arguments_and_result_once():
    calls = []
    def custom(*values):
        calls.append(values)
        return .1
    sample = EaseFactory.stop_motion(4, custom_ease=custom)
    assert sample(.49, 1.1, 2.5, .4) == .10000000149011612
    assert calls == [(.25, 1.100000023841858, 2.5, .4000000059604645)]


@pytest.mark.parametrize("ease", [Ease.INTERNAL_ZERO, Ease.INTERNAL_CUSTOM])
def test_reserved_factory_eases_use_the_default_quadratic_function(ease):
    sample = EaseFactory.stop_motion(4, ease=ease)
    expected = EaseManager.to_ease_function(Ease.OUT_QUAD)(.25, 1., 1., 0.)
    assert sample(.49, 1., 1., 0.) == expected


def test_nonfinite_clock_inputs_use_ordered_comparison_and_ieee_remainder():
    sample = EaseFactory.stop_motion(4, custom_ease=lambda t, d, a, p: t)
    assert sample(.49, math.nan, 1., 0.) == .49000000953674316
    assert math.isnan(sample(math.nan, 1., 1., 0.))
    assert sample(math.inf, 1., 1., 0.) == math.inf
    assert math.isnan(sample(-math.inf, 1., 1., 0.))
    assert sample(.49, math.inf, 1., 0.) == .25


def test_factory_captures_default_ease_and_keeps_callback_cycles_collectable():
    from infernux_tween.core import _default_manager
    previous = _default_manager.default_ease_type
    try:
        _default_manager.default_ease_type = Ease.LINEAR
        sample = EaseFactory.stop_motion(4)
        _default_manager.default_ease_type = Ease.IN_QUAD
        assert sample(.49, 1., 1., 0.) == .25
    finally:
        _default_manager.default_ease_type = previous
    class Owner:
        def evaluate(self, time, duration, amplitude, period):
            return time
    owner = Owner()
    owner.sample = EaseFactory.stop_motion(4, custom_ease=owner.evaluate)
    reference = weakref.ref(owner)
    del owner
    gc.collect()
    assert reference() is None
