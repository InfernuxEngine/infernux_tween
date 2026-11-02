"""Segment boundaries and their live playback share one float clock."""
import math

import pytest

from infernux.lib import Vector3
from infernux.lib._Infernux import _tween_array_duration
from infernux_tween import AxisConstraint, Ease, TweenManager


def test_accumulated_duration_finishes_on_the_stored_endpoint():
    manager = TweenManager()
    value = [Vector3(0, 0, 0)]
    tween = manager.to_array(lambda: value[0], lambda v: value.__setitem__(0, v),
                             [Vector3(1, 0, 0), Vector3(2, 0, 0)], [1 / 12, 1 / 6])
    tween.set_ease(Ease.LINEAR).set_auto_kill(False)
    try:
        assert tween.duration() == .25
        tween.goto(.25)
        assert tween.is_complete() and tween.completed_loops() == 1
        assert tuple(value[0]) == pytest.approx((2, 0, 0), abs=1e-6)
    finally:
        manager.clear()


def test_duration_accumulation_stores_each_float_boundary():
    assert _tween_array_duration([.1] * 10) == 1.0000001192092896
    assert _tween_array_duration([.1, -.1]) == 0
    assert math.isinf(_tween_array_duration([math.inf]))
    assert math.isnan(_tween_array_duration([math.nan]))


def test_zero_length_array_selects_the_first_reachable_segment():
    manager = TweenManager()
    value = [Vector3(0, 0, 0)]
    tween = manager.to_array(lambda: value[0], lambda v: value.__setitem__(0, v),
                             [Vector3(1, 2, 3), Vector3(7, 8, 9)], [0, 0])
    tween.set_auto_kill(False)
    try:
        tween.goto(0)
        assert tween.is_complete()
        assert tuple(value[0]) == (1, 2, 3)
    finally:
        manager.clear()


def test_zero_length_array_keeps_axis_constraints_and_snapping():
    manager = TweenManager()
    value = [Vector3(11, 12, 13)]
    tween = manager.to_array(lambda: value[0], lambda v: value.__setitem__(0, v),
                             [Vector3(1.5, 2.5, 3.5), Vector3(7, 8, 9)], [0, 0])
    tween.set_options(AxisConstraint.X, True).set_auto_kill(False)
    try:
        tween.goto(0)
        assert tuple(value[0]) == (2, 12, 13)
    finally:
        manager.clear()
