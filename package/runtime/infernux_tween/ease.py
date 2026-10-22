"""Analytic easing curves; custom callables use the same normalized input."""

from enum import Enum
from math import cos, pi, sin, sqrt


class Ease(str, Enum):
    Linear = "Linear"
    InSine = "InSine"
    OutSine = "OutSine"
    InOutSine = "InOutSine"
    InQuad = "InQuad"
    OutQuad = "OutQuad"
    InOutQuad = "InOutQuad"
    InCubic = "InCubic"
    OutCubic = "OutCubic"
    InOutCubic = "InOutCubic"
    InQuart = "InQuart"
    OutQuart = "OutQuart"
    InOutQuart = "InOutQuart"
    InQuint = "InQuint"
    OutQuint = "OutQuint"
    InOutQuint = "InOutQuint"
    InExpo = "InExpo"
    OutExpo = "OutExpo"
    InOutExpo = "InOutExpo"
    InCirc = "InCirc"
    OutCirc = "OutCirc"
    InOutCirc = "InOutCirc"
    InBack = "InBack"
    OutBack = "OutBack"
    InOutBack = "InOutBack"
    InElastic = "InElastic"
    OutElastic = "OutElastic"
    InOutElastic = "InOutElastic"
    InBounce = "InBounce"
    OutBounce = "OutBounce"
    InOutBounce = "InOutBounce"


def _bounce(t):
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


def resolve_ease(ease):
    if callable(ease):
        return ease
    if not isinstance(ease, str):
        from infernux.graph.ramp import AnimationCurve
        from .curve import EaseCurve
        if isinstance(ease, AnimationCurve):
            return EaseCurve(ease.keys, ease.pre_wrap, ease.post_wrap)
    name = Ease(ease).value
    if name == "Linear":
        return lambda t: t
    if name == "InOutBack":
        overshoot = 1.70158 * 1.525
        return lambda t: ((2 * t) ** 2 * ((overshoot + 1) * 2 * t - overshoot) / 2
                          if t < 0.5 else ((2 * t - 2) ** 2 * ((overshoot + 1) * (2 * t - 2) + overshoot) + 2) / 2)
    if name == "InOutElastic":
        return lambda t: (t if t in (0, 1) else
                          -(2 ** (20 * t - 10) * sin((20 * t - 11.125) * 2 * pi / 4.5)) / 2 if t < 0.5 else
                          2 ** (-20 * t + 10) * sin((20 * t - 11.125) * 2 * pi / 4.5) / 2 + 1)
    direction, family = next((p, name[len(p):]) for p in ("InOut", "In", "Out") if name.startswith(p))
    if family in {"Quad", "Cubic", "Quart", "Quint"}:
        power = {"Quad": 2, "Cubic": 3, "Quart": 4, "Quint": 5}[family]
        inward = lambda t: t ** power
    elif family == "Sine":
        inward = lambda t: 1 - cos(t * pi / 2)
    elif family == "Expo":
        inward = lambda t: 0.0 if t == 0 else 2 ** (10 * t - 10)
    elif family == "Circ":
        inward = lambda t: 1 - sqrt(max(0.0, 1 - t * t))
    elif family == "Back":
        inward = lambda t: 2.70158 * t ** 3 - 1.70158 * t * t
    elif family == "Elastic":
        inward = lambda t: t if t in (0, 1) else -(2 ** (10 * t - 10)) * sin((t * 10 - 10.75) * 2 * pi / 3)
    else:
        inward = lambda t: 1 - _bounce(1 - t)
    if direction == "In":
        return inward
    if direction == "Out":
        return lambda t: 1 - inward(1 - t)
    return lambda t: inward(2 * t) / 2 if t < 0.5 else 1 - inward(2 - 2 * t) / 2
