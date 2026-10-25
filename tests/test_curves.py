import pytest

from infernux.graph.ramp import AnimationCurve, Keyframe
from infernux_tween import EaseCurve, TweenManager


def test_curve_uses_authored_tangents_and_wraps_on_both_sides():
    keys = (Keyframe(0, 0, out_tangent=1), Keyframe(1, 1, in_tangent=1))
    curve = EaseCurve(keys, pre_wrap='repeat', post_wrap='ping_pong')
    assert [curve(t) for t in (-0.25, 0, 0.25, 1, 1.25, 2.25)] == pytest.approx([0.75, 0, 0.25, 1, 0.75, 0.25])
    smooth = EaseCurve((Keyframe(0, 0), Keyframe(1, 1)))
    assert smooth(0.25) == pytest.approx(0.15625)
    assert smooth(-1) == 0 and smooth(2) == 1


def test_cpu_curve_accepts_many_keys_and_engine_curve_is_a_set_ease_overload():
    keys = tuple(Keyframe(i/64, (i/64)**2, 2*i/64, 2*i/64) for i in range(65))
    curve = EaseCurve(keys)
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
    assert value[0] == 6 and calls == [(1.5, 3, 2.5, 0.4)]
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
    assert value[0] == pytest.approx(10*0.25/1.1) and calls[-1] == (0.25, 1.1, 2.5, 0.4)
    manager.update(1)
    assert value[0] == 10 and calls[-1][0] == 1.1
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
            assert samples == [[0.4, 0.4, 0.4, 0.4]]
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
