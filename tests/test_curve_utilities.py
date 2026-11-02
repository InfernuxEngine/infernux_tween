"""Curve utility contracts include extrapolation, append semantics and native batches."""
import sys
import threading

import numpy as np
import pytest

from infernux import AnimationCurve, Keyframe
from infernux.lib import Vector3
import infernux_tween as api


def controls():
    return Vector3(), Vector3(0, 2, 0), Vector3(2, 0, 0), Vector3(2, 2, 0)


@pytest.mark.parametrize('factor,expected', [
    (-.5, (2, -4.5, 0)), (0., (0, 0, 0)), (.25, (.3125, 1.125, 0)),
    (.5, (1, 1.5, 0)), (1., (2, 0, 0)), (1.5, (0, -4.5, 0)),
])
def test_cubic_segment_uses_the_control_point_order_and_allows_extrapolation(factor, expected):
    first, first_control, last, last_control = controls()
    value = api.TweenCurve.CubicBezier.get_point_on_segment(start_point=first,
        start_control_point=first_control, end_point=last, end_control_point=last_control, factor=factor)
    assert tuple(value) == expected
    assert api.TweenCurve.CubicBezier is api.CubicBezier


@pytest.mark.parametrize('resolution', [-2, 0, 1, 2, 3, 10, 42, 103])
def test_cubic_cloud_resolution_counts_points_and_appends_without_clearing(resolution):
    points = controls()
    cloud = api.CubicBezier.get_segment_point_cloud(*points, resolution=resolution)
    count = max(2, resolution)
    assert len(cloud) == count
    step = np.float32(1) / np.float32(count - 1)
    for index, value in enumerate(cloud):
        expected = api.CubicBezier.get_point_on_segment(*points, float(step * np.float32(index)))
        assert tuple(value) == tuple(expected)
    sentinel = Vector3(9, 8, 7)
    target = [sentinel]
    first, first_control, last, last_control = points
    result = api.CubicBezier.get_segment_point_cloud(add_to_list=target, start_point=first,
        start_control_point=first_control, end_point=last, end_control_point=last_control, resolution=resolution)
    assert result is None and target[0] is sentinel
    assert [tuple(value) for value in target[1:]] == [tuple(value) for value in cloud]


def test_cubic_cloud_default_and_mixed_append_overload_share_the_same_samples():
    points = controls()
    cloud = api.CubicBezier.get_segment_point_cloud(*points)
    assert len(cloud) == 10
    target = []
    assert api.CubicBezier.get_segment_point_cloud(target, *points, resolution=3) is None
    assert [tuple(value) for value in target] == [(0, 0, 0), (1, 1.5, 0), (2, 0, 0)]


def test_large_cubic_cloud_releases_gil_after_capturing_input_values():
    armed, observed = threading.Event(), threading.Event()
    points = controls()
    def mutate():
        armed.wait()
        points[0].x = 99
        observed.set()
    previous = sys.getswitchinterval()
    worker = threading.Thread(target=mutate)
    try:
        sys.setswitchinterval(10)
        worker.start()
        armed.set()
        small = api.CubicBezier.get_segment_point_cloud(*points, resolution=2)
        assert not observed.is_set() and tuple(small[0]) == (0, 0, 0)
        large = api.CubicBezier.get_segment_point_cloud(*points, resolution=1_000_000)
        assert observed.is_set() and len(large) == 1_000_000
        assert tuple(large[0]) == (0, 0, 0) and points[0].x == 99
    finally:
        sys.setswitchinterval(previous)
        armed.set()
        worker.join(timeout=5)


def test_ease_factory_reuses_the_public_function_and_observes_live_curve_edits():
    assert api.EaseFactory.stop_motion is api.stop_motion
    sample = api.EaseFactory.stop_motion(motion_fps=4, ease=api.Ease.LINEAR)
    assert sample(.49, 1., 1., 0.) == .25
    curve = AnimationCurve.linear(0, 0, 1, 1)
    sample = api.EaseFactory.stop_motion(motion_fps=4, anim_curve=curve)
    assert sample(.49, 1., 1., 0.) == .25
    curve.set_keys([Keyframe(0, 0, 2, 2), Keyframe(1, 2, 2, 2)])
    assert sample(.49, 1., 1., 0.) == .5
    calls = []
    def custom(time, duration, amplitude, period):
        calls.append((time, duration, amplitude, period))
        return time / duration
    sample = api.EaseFactory.stop_motion(4, custom_ease=custom)
    assert sample(.49, 1., 2.5, .4) == .25
    assert calls == [(.25, 1., 2.5, .4000000059604645)]
