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
    manager.To(lambda: value[0], lambda x: value.__setitem__(0, x), 10.0, 1).SetEase(authored)
    manager.Update(0.25)
    assert value[0] == pytest.approx(1.5625)
    manager.Clear()
