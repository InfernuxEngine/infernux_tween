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
