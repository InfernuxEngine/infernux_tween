"""Public analytical helpers and their native geometry integration."""
import struct
import numpy as np
import pytest
from infernux.lib import Vector2
import infernux_tween as tween


@pytest.mark.parametrize('method,time,expected', [('ease_in', .5, .234375),
    ('ease_out', .5, .765625), ('ease_in_out', .25, .1171875),
    ('ease_in_out', .75, .8828125)])
def test_bounce_public_helpers_accept_named_ease_parameters(method, time, expected):
    value = getattr(tween.Bounce, method)(time=time, duration=1.,
        unused_overshoot_or_amplitude=99., unused_period=-3.)
    assert type(value) is float and value == expected


@pytest.mark.parametrize('method', ['ease_in', 'ease_out', 'ease_in_out'])
def test_bounce_helpers_keep_both_endpoints(method):
    ease = getattr(tween.Bounce, method)
    assert ease(0., 2., 0., 0.) == 0.
    assert ease(2., 2., 0., 0.) == 1.


@pytest.mark.parametrize('method,expected', [('ease', .5), ('ease_in', .25),
                                           ('ease_out', .75), ('ease_in_out', .5)])
def test_flash_helpers_control_one_half_pulse(method, expected):
    ease = getattr(tween.Flash, method)
    assert ease(time=.125, duration=1., overshoot_or_amplitude=4., period=0.) == expected
    assert ease(0., 1., 4., 0.) == 0.
    assert ease(1., 1., 4., 0.) == 0.
    assert ease(1., 1., 3., 0.) == 1.


def test_public_helper_can_drive_a_typed_tween_callback():
    manager, values = tween.TweenManager(), []
    try:
        handle = manager.to(lambda: np.float32(0), values.append, np.float32(8), 1.)
        handle.set_ease(tween.Bounce.ease_out).goto(.5)
        assert type(values[-1]) is np.float32 and values[-1] == np.float32(6.125)
    finally:
        manager.clear()


@pytest.mark.parametrize('degrees,expected', [(0., (2., 5.)), (90., (4., 3.)),
                                             (180., (2., 1.)), (270., (0., 3.))])
def test_circle_points_start_up_and_turn_clockwise(degrees, expected):
    center = Vector2(2., 3.)
    point = tween.TweenUtils.get_point_on_circle(center=center, radius=2., degrees=degrees)
    assert type(point) is Vector2
    assert tuple(point) == pytest.approx(expected, abs=1e-6)
    point.x = 10.
    assert tuple(center) == (2., 3.)


def test_circle_utility_keeps_single_width_radius_without_a_python_geometry_object():
    point = tween.TweenUtils.get_point_on_circle(Vector2(), 1.1, 90.)
    single = struct.unpack('<f', struct.pack('<f', 1.1))[0]
    assert point.x == single and point.y == 0.


def test_public_ease_utility_narrows_arguments_and_its_return_factor():
    single = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]
    assert tween.EaseManager.evaluate(tween.Ease.LINEAR, None, 1., 3., 0., 0.) == single(1 / 3)
    assert tween.EaseManager.evaluate(tween.Ease.LINEAR, None, 1.1, 3.1, 0., 0.) == single(single(1.1) / single(3.1))
