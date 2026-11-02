import copy
import math

import numpy as np

import pytest

from infernux.graph.ramp import AnimationCurve, Keyframe, WeightedMode, WrapMode
from infernux_tween import EaseCurve, TweenManager


@pytest.mark.parametrize('duration', [1e-300, -1e-300, 1e300, 3.7, 0., -0.])
def test_ease_batches_preserve_division_before_scaling_and_ieee_boundaries(duration):
    curve = AnimationCurve.linear(0, 0, 1e20, 1)
    ease = EaseCurve(curve)
    finite = [duration * progress for progress in (-.25, 0., .25, .5, .75, 1., 1.25)]
    times = np.asarray([*finite, -1., 1., -math.inf, math.inf, math.nan], dtype=np.float64)
    with np.errstate(all='ignore'):
        mapped = (times / np.float64(duration)) * curve[curve.length - 1].time
    expected = np.asarray([curve.evaluate(time) for time in mapped])
    scalar = np.asarray([ease.evaluate(time, duration, 0, 0) for time in times])
    returned = np.asarray(ease.evaluate_many(times, duration))
    output = np.empty_like(times)
    ease.evaluate_into(times, output, duration)
    assert np.array_equal(scalar, expected, equal_nan=True)
    assert np.array_equal(returned, expected, equal_nan=True)
    assert np.array_equal(output, expected, equal_nan=True)
    # Input/output aliasing remains legal; mapping must read each original row.
    alias = times.copy()
    ease.evaluate_into(alias, alias, duration)
    assert np.array_equal(alias, expected, equal_nan=True)
    if duration == 1e-300:
        assert scalar[3] == .5


def test_live_ease_refreshes_sampling_domain_wrap_and_repopulated_empty_asset():
    curve = AnimationCurve.linear(0, 0, 2, 1)
    ease = EaseCurve(curve)
    assert ease(.5) == .5
    curve.keys = [Keyframe(0, 0), Keyframe(4, 2)]
    assert ease(.5) == 1
    curve.post_wrap_mode = WrapMode.LOOP
    assert ease(1.25) == .3125
    assert ease.evaluate_many([.5, 1.25]) == [1, .3125]
    curve.clear_keys()
    with pytest.raises(IndexError):
        ease(.5)
    curve.keys = [Keyframe(0, 3), Keyframe(8, 5)]
    assert ease(.5) == 4


def test_authoring_edits_preserve_copied_curve_and_existing_native_samples():
    curve = AnimationCurve(Keyframe(0, 0, 0, 4), Keyframe(1, 1, -2, 0), Keyframe(2, 4))
    retained = copy.copy(curve)
    snapshot = retained._native_snapshot()
    retained_keys = retained.keys
    sample = snapshot.evaluate(.5)
    content = retained.get_hash_code()
    curve.smooth_tangents(1, .35)
    curve.add_key(.5, 3)
    curve.move_key(3, Keyframe(3, 5))
    curve.remove_key(0)
    assert retained.keys == retained_keys
    assert retained.get_hash_code() == content
    assert retained.evaluate(.5) == snapshot.evaluate(.5) == sample
    assert [key.time for key in curve.keys] == [.5, 1, 3]
    assert curve.evaluate(.5) == 3


@pytest.mark.parametrize('points,weight,expected', [
    ([(0, -2), (.37, -1), (.74, 2)], 0, 5.405405044555664),
    ([(8.963085174560547, -30.215669631958008),
      (10.79347038269043, 21.45990753173828),
      (12.165143966674805, -18.393827438354492)], 0, -.4113740921020508),
    ([(1.3597121238708496, 20.459033966064453),
      (2.8347935676574707, 16.410547256469727),
      (4.064260005950928, 21.702251434326172)], -2.904039144515991, 11.014519691467285),
    ([(-3.8683218955993652, -46.89865493774414),
      (-2.466489315032959, 27.56816291809082),
      (.43076181411743164, 6.046167850494385)], -1, -7.42841911315918),
    ([(-4.372811317443848, -41.00845718383789),
      (-1.926217794418335, 39.014984130859375),
      (-1.0628037452697754, -15.236421585083008)], -1, -62.833587646484375),
])
def test_smoothing_keeps_float32_rounding_for_cancellation_and_extrapolation(points, weight, expected):
    curve = AnimationCurve(keys=[Keyframe(t, v) for t, v in points])
    curve.smooth_tangents(1, weight)
    assert curve[1].in_tangent == curve[1].out_tangent == expected


@pytest.mark.parametrize('mode', list(WeightedMode.__members__.values()))
def test_smoothing_resets_connected_weights_and_preserves_weighted_mode(mode):
    curve = AnimationCurve(Keyframe(0, 0, 1, 2, .2, .7, mode),
                           Keyframe(1, 2, 3, 4, .2, .7, mode),
                           Keyframe(2, 3, 5, 6, .2, .7, mode))
    third = pytest.approx(1 / 3, abs=1e-8)
    curve.smooth_tangents(1, 0)
    middle = curve[1]
    assert middle.in_tangent == middle.out_tangent == 1.5
    assert middle.in_weight == middle.out_weight == third
    assert middle.weighted_mode == mode
    before = curve[0]
    curve.smooth_tangents(0, 0)
    assert curve[0].in_weight == before.in_weight
    assert curve[0].out_weight == third and curve[0].weighted_mode == mode
    before = curve[2]
    curve.smooth_tangents(2, 0)
    assert curve[2].out_weight == before.out_weight
    assert curve[2].in_weight == third and curve[2].weighted_mode == mode


def test_smoothing_singleton_preserves_authored_key_and_weight_metadata():
    key = Keyframe(.2, 3, 7, -2, .2, .7, WeightedMode.BOTH, tangent_mode=17)
    curve = AnimationCurve(key)
    curve.smooth_tangents(0, 1)
    assert curve[0] == key


def test_curve_comparison_ignores_legacy_tangent_mode_but_keeps_wrap_modes():
    curve = AnimationCurve.linear(0, 0, 1, 1)
    copy = AnimationCurve()
    copy.copy_from(curve)
    key = copy[0]
    key.tangent_mode = 17
    copy.move_key(0, key)
    assert copy.equals(curve)
    assert copy[0] != curve[0]  # Keyframe values still include their own metadata.
    assert copy.get_hash_code() != curve.get_hash_code()
    copy.copy_from(curve)
    copy.pre_wrap_mode = WrapMode.LOOP
    assert not copy.equals(curve)
    assert copy.get_hash_code() == curve.get_hash_code()
    assert AnimationCurve().get_hash_code() == 0


def test_smoothing_live_weighted_curve_updates_existing_ease_and_tween():
    curve = AnimationCurve(Keyframe(0, 0, 0, 4, .2, .8, WeightedMode.BOTH),
                           Keyframe(1, 1, -2, 0, .1, .5, WeightedMode.BOTH))
    ease = EaseCurve(curve)
    manager, value = TweenManager(), [0.]
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1.).set_ease(curve)
    tween.goto(.25)
    previous = value[0]
    snapshot = curve._native_snapshot()
    curve.smooth_tangents(0, 0)
    curve.smooth_tangents(1, 0)
    tween.goto(.25)
    assert value[0] != previous
    assert value[0] == pytest.approx(2.5, abs=1e-6)
    assert ease(.25) == pytest.approx(.25, abs=1e-7)
    assert curve._native_snapshot() is not snapshot
    manager.clear()


def test_curve_uses_authored_tangents_and_wraps_on_both_sides():
    keys = (Keyframe(0, 0, out_tangent=1), Keyframe(1, 1, in_tangent=1))
    curve = EaseCurve(AnimationCurve(keys, pre_wrap='repeat', post_wrap='ping_pong'))
    assert [curve(t) for t in (-0.25, 0, 0.25, 1, 1.25, 2.25)] == pytest.approx([0.75, 0, 0.25, 1, 0.75, 0.25])
    smooth = EaseCurve(AnimationCurve(Keyframe(0, 0), Keyframe(1, 1)))
    assert smooth(0.25) == pytest.approx(0.15625)
    assert smooth(-1) == 0 and smooth(2) == 1


def test_cpu_curve_accepts_many_keys_and_engine_curve_is_a_set_ease_overload():
    keys = tuple(Keyframe(i/64, (i/64)**2, 2*i/64, 2*i/64) for i in range(65))
    curve = EaseCurve(AnimationCurve(keys=keys))
    assert curve(0.317) == pytest.approx(0.317**2)
    manager, value = TweenManager(), [0.0]
    authored = AnimationCurve((Keyframe(0, 0), Keyframe(1, 1)))
    manager.to(lambda: value[0], lambda x: value.__setitem__(0, x), 10.0, 1).set_ease(authored)
    manager.update(0.25)
    assert value[0] == pytest.approx(1.5625)
    manager.clear()


def test_ease_overloads_keep_real_time_parameters_and_flash_oscillations():
    from infernux_tween import Ease
    manager, calls, value = TweenManager(), [], [0.0]
    manager.default_ease_overshoot_or_amplitude, manager.default_ease_period = 2.5, 0.4
    def custom(time, duration, amplitude, period):
        calls.append((time, duration, amplitude, period))
        return time/duration
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 12., 3).set_ease(custom)
    manager.update(1.5)
    assert value[0] == 6 and calls == [(1.5, 3, 2.5, 0.4000000059604645)]
    tween.set_ease(Ease.OUT_BACK, overshoot=2.5).goto(1.5)
    assert value[0] == pytest.approx(14.25)
    tween.set_ease(Ease.FLASH, 4., 0.)
    assert [tween._ease(time) for time in (0, 0.25, 0.5, 0.75, 1)] == [0, 1, 0, 1, 0]
    with pytest.raises(TypeError):
        tween.set_ease('Linear')
    manager.clear()


def test_eased_value_and_stop_motion_share_curve_and_real_time_easing():
    from infernux.lib import Vector3
    from infernux_tween import Ease, eased_value, stop_motion
    assert eased_value(2., 10., 0.5, Ease.OUT_QUAD) == 8
    assert tuple(eased_value(Vector3(0, 2, 4), Vector3(8, 10, 12), 0.5, Ease.LINEAR)) == (4, 6, 8)
    curve = AnimationCurve((Keyframe(0, 0), Keyframe(1, 1)))
    assert eased_value(0., 10., 0.25, ease_curve=curve) == 1.5625
    calls = []
    def custom(time, duration, amplitude, period):
        calls.append((time, duration, amplitude, period))
        return time/duration
    manager, value = TweenManager(), [0.0]
    manager.default_ease_overshoot_or_amplitude, manager.default_ease_period = 2.5, 0.4
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1.1)
    tween.set_ease(stop_motion(4, custom_ease=custom))
    manager.update(0.49)
    assert value[0] == pytest.approx(10*0.25/1.1)
    assert calls[-1] == (0.25, 1.100000023841858, 2.5, 0.4000000059604645)
    manager.update(1)
    assert value[0] == 10 and calls[-1][0] == 1.100000023841858
    tween = manager.to(lambda: 0., lambda v: None, 1., 1).set_ease(stop_motion(4, anim_curve=curve))
    assert tween._ease(0.49) == 0.15625
    manager.clear()


def test_virtual_factories_keep_value_callback_and_timer_lifecycle_contracts():
    import infernux_tween as api
    from infernux.lib import Vector2, Vector3
    for factory, start, end in ((api.virtual.float, 2, 6), (api.virtual.int, 2, 6),
            (api.virtual.vector2, Vector2(0, 2), Vector2(8, 10)),
            (api.virtual.vector3, Vector3(0, 2, 4), Vector3(8, 10, 12)),
            (api.virtual.color, [0., 0., 0., 0.], [1., 1., 1., 1.])):
        samples = []
        value = factory(start, end, 1., samples.append).set_ease(api.Ease.LINEAR)
        api.update(0.4)
        if isinstance(start, list):
            assert samples[0] == pytest.approx([0.4, 0.4, 0.4, 0.4])
        elif isinstance(start, (Vector2, Vector3)):
            assert tuple(samples[0]) == pytest.approx(tuple(start+(end-start)*0.4))
        else:
            assert samples == pytest.approx([3.6 if factory is api.virtual.float else 4])
        value.on_update(lambda: None)
        api.update(0.6)
        assert len(samples) == 1 and not value.is_active()
    calls = []
    independent = api.delayed_call(0.5, lambda: calls.append('unscaled'))
    scaled = api.delayed_call(0.5, lambda: calls.append('scaled'), ignore_time_scale=False)
    cancelled = api.delayed_call(0.1, lambda: calls.append('cancelled'))
    cancelled.kill()
    api.update(0, 0.5)
    assert calls == ['unscaled'] and not independent.is_active() and scaled.is_active()
    scaled.pause()
    api.update(1)
    assert calls == ['unscaled']
    scaled.restart()
    api.update(0.5)
    assert calls == ['unscaled', 'scaled'] and not scaled.is_active()
    api.clear()
