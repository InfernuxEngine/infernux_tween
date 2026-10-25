"""Analytic curves compiled once for normalized sampling."""

from enum import Enum
from math import asin, ceil, cos, floor, pi, sin, sqrt
from typing import Callable, overload

from infernux.graph.ramp import AnimationCurve


class Ease(Enum):
    UNSET = "Unset"
    LINEAR = "Linear"
    IN_SINE = "InSine"
    OUT_SINE = "OutSine"
    IN_OUT_SINE = "InOutSine"
    IN_QUAD = "InQuad"
    OUT_QUAD = "OutQuad"
    IN_OUT_QUAD = "InOutQuad"
    IN_CUBIC = "InCubic"
    OUT_CUBIC = "OutCubic"
    IN_OUT_CUBIC = "InOutCubic"
    IN_QUART = "InQuart"
    OUT_QUART = "OutQuart"
    IN_OUT_QUART = "InOutQuart"
    IN_QUINT = "InQuint"
    OUT_QUINT = "OutQuint"
    IN_OUT_QUINT = "InOutQuint"
    IN_EXPO = "InExpo"
    OUT_EXPO = "OutExpo"
    IN_OUT_EXPO = "InOutExpo"
    IN_CIRC = "InCirc"
    OUT_CIRC = "OutCirc"
    IN_OUT_CIRC = "InOutCirc"
    IN_BACK = "InBack"
    OUT_BACK = "OutBack"
    IN_OUT_BACK = "InOutBack"
    IN_ELASTIC = "InElastic"
    OUT_ELASTIC = "OutElastic"
    IN_OUT_ELASTIC = "InOutElastic"
    IN_BOUNCE = "InBounce"
    OUT_BOUNCE = "OutBounce"
    IN_OUT_BOUNCE = "InOutBounce"
    FLASH = "Flash"
    IN_FLASH = "InFlash"
    OUT_FLASH = "OutFlash"
    IN_OUT_FLASH = "InOutFlash"


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


def _flash(t, count, weight, shape):
    step = ceil(t * count)
    forward = step % 2 != 0
    phase = t * count - (step - 1)
    if not forward:
        phase = 1 - phase
    if shape == "InFlash":
        phase *= phase
    elif shape == "OutFlash":
        phase = phase * (2 - phase)
    elif shape == "InOutFlash":
        phase = 2 * phase * phase if phase < 0.5 else 1 - 2 * (1 - phase) ** 2
    if forward == (int(count) % 2 == 0):
        step += 1
    correction = 0.0
    if weight > 0:
        tail = count - int(count)
        if int(count) % 2:
            tail = 1 - tail
        correction = tail * step / count
        weighted = phase * (count - step) / count
    elif weight < 0:
        weight = -weight
        weighted = phase * step / count
    else:
        weighted = 0.0
    return min(1.0, phase + (weighted - phase) * weight + correction)


@overload
def stop_motion(motion_fps: int, ease: Ease|None=None) -> Callable[[float, float, float, float], float]: ...
@overload
def stop_motion(motion_fps: int, anim_curve: AnimationCurve) -> Callable[[float, float, float, float], float]: ...
@overload
def stop_motion(motion_fps: int, custom_ease: Callable[[float, float, float, float], float]) -> Callable[[float, float, float, float], float]: ...
def stop_motion(motion_fps, ease=None, *, anim_curve=None, custom_ease=None):
    if type(motion_fps) is not int or motion_fps <= 0:
        raise ValueError('motion_fps must be a positive integer')
    if sum(value is not None for value in (ease, anim_curve, custom_ease)) > 1:
        raise TypeError('provide one ease, anim_curve or custom_ease')
    from .core import _default_manager
    source = next((value for value in (ease, anim_curve, custom_ease) if value is not None), _default_manager.default_ease_type)
    configuration, sample = None, None

    def snapped(time, duration, amplitude, period):
        nonlocal configuration, sample
        key = duration, amplitude, period
        if configuration != key:
            sample = resolve_ease(source, amplitude, period, lambda: duration)
            configuration = key
        time = duration if time >= duration else floor(time*motion_fps)/motion_fps
        return sample(time/duration if duration else 1.0)
    return snapped


def resolve_ease(ease, overshoot_or_amplitude=1.70158, period=0.0, duration=None):
    from .curve import EaseCurve
    if isinstance(ease, AnimationCurve):
        return EaseCurve(ease.keys, ease.pre_wrap, ease.post_wrap)
    if isinstance(ease, EaseCurve):
        return ease
    if callable(ease):
        clock = duration or (lambda: 1.0)
        def custom(t):
            seconds = clock()
            return ease(t * seconds, seconds, overshoot_or_amplitude, period)
        return custom
    if not isinstance(ease, Ease):
        raise TypeError("ease must be Ease, AnimationCurve or a four-argument function")
    name = ease.value
    if name == "Unset":
        name = "OutQuad"
    if name == "Linear":
        return lambda t: t
    if name.endswith("Flash"):
        if overshoot_or_amplitude <= 0:
            raise ValueError("Flash count must be positive")
        return lambda t: _flash(t, overshoot_or_amplitude, period, name)
    if name == "InOutBack":
        overshoot = overshoot_or_amplitude * 1.525
        return lambda t: ((2 * t) ** 2 * ((overshoot + 1) * 2 * t - overshoot) / 2
                          if t < 0.5 else ((2 * t - 2) ** 2 * ((overshoot + 1) * (2 * t - 2) + overshoot) + 2) / 2)
    if name.endswith("Elastic"):
        amplitude = max(1.0, overshoot_or_amplitude)
        def elastic(t):
            if t in (0, 1):
                return t
            seconds = duration() if duration is not None else 1.0
            wave = period / seconds if period else (0.45 if name == "InOutElastic" else 0.3)
            shift = wave / (2 * pi) * asin(1 / amplitude)
            if name == "InElastic":
                return -amplitude * 2 ** (10 * (t - 1)) * sin((t - 1 - shift) * 2 * pi / wave)
            if name == "OutElastic":
                return amplitude * 2 ** (-10 * t) * sin((t - shift) * 2 * pi / wave) + 1
            t = 2 * t - 1
            return (-0.5 * amplitude * 2 ** (10 * t) * sin((t - shift) * 2 * pi / wave)
                    if t < 0 else amplitude * 2 ** (-10 * t) * sin((t - shift) * 2 * pi / wave) * 0.5 + 1)
        return elastic
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
        inward = lambda t: (overshoot_or_amplitude + 1) * t ** 3 - overshoot_or_amplitude * t * t
    else:
        inward = lambda t: 1 - _bounce(1 - t)
    if direction == "In":
        return inward
    if direction == "Out":
        return lambda t: 1 - inward(1 - t)
    return lambda t: inward(2 * t) / 2 if t < 0.5 else 1 - inward(2 - 2 * t) / 2
