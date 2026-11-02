"""Analytic curves compiled once for normalized sampling."""

from enum import Enum
from functools import lru_cache, partial
from infernux.lib._Infernux import _EaseKernel, _StopMotionClock, _evaluate_builtin_ease, _evaluate_custom_ease, _sample_custom_ease
from typing import Callable, TYPE_CHECKING, overload

from infernux.graph.ramp import AnimationCurve

if TYPE_CHECKING:
    from .core import Tween


class Ease(Enum):
    UNSET = 0
    LINEAR = 1
    IN_SINE = 2
    OUT_SINE = 3
    IN_OUT_SINE = 4
    IN_QUAD = 5
    OUT_QUAD = 6
    IN_OUT_QUAD = 7
    IN_CUBIC = 8
    OUT_CUBIC = 9
    IN_OUT_CUBIC = 10
    IN_QUART = 11
    OUT_QUART = 12
    IN_OUT_QUART = 13
    IN_QUINT = 14
    OUT_QUINT = 15
    IN_OUT_QUINT = 16
    IN_EXPO = 17
    OUT_EXPO = 18
    IN_OUT_EXPO = 19
    IN_CIRC = 20
    OUT_CIRC = 21
    IN_OUT_CIRC = 22
    IN_BACK = 26
    OUT_BACK = 27
    IN_OUT_BACK = 28
    IN_ELASTIC = 23
    OUT_ELASTIC = 24
    IN_OUT_ELASTIC = 25
    IN_BOUNCE = 29
    OUT_BOUNCE = 30
    IN_OUT_BOUNCE = 31
    FLASH = 32
    IN_FLASH = 33
    OUT_FLASH = 34
    IN_OUT_FLASH = 35
    INTERNAL_ZERO = 36
    INTERNAL_CUSTOM = 37

    @property
    def label(self):
        if self.value >= 36:
            return "INTERNAL_" + ("Zero" if self == Ease.INTERNAL_ZERO else "Custom")
        return "".join(part.title() for part in self.name.split("_"))


class Bounce:
    """Piecewise bounce functions with the standard four-argument ease contract."""

    @staticmethod
    def ease_in(time: float, duration: float, unused_overshoot_or_amplitude: float, unused_period: float) -> float:
        return _evaluate_builtin_ease(29, time, duration, unused_overshoot_or_amplitude, unused_period)

    @staticmethod
    def ease_out(time: float, duration: float, unused_overshoot_or_amplitude: float, unused_period: float) -> float:
        return _evaluate_builtin_ease(30, time, duration, unused_overshoot_or_amplitude, unused_period)

    @staticmethod
    def ease_in_out(time: float, duration: float, unused_overshoot_or_amplitude: float, unused_period: float) -> float:
        return _evaluate_builtin_ease(31, time, duration, unused_overshoot_or_amplitude, unused_period)


class Flash:
    """Alternating pulses, with count and weighting supplied as ease options."""

    @staticmethod
    def ease(time: float, duration: float, overshoot_or_amplitude: float, period: float) -> float:
        return _evaluate_builtin_ease(32, time, duration, overshoot_or_amplitude, period)

    @staticmethod
    def ease_in(time: float, duration: float, overshoot_or_amplitude: float, period: float) -> float:
        return _evaluate_builtin_ease(33, time, duration, overshoot_or_amplitude, period)

    @staticmethod
    def ease_out(time: float, duration: float, overshoot_or_amplitude: float, period: float) -> float:
        return _evaluate_builtin_ease(34, time, duration, overshoot_or_amplitude, period)

    @staticmethod
    def ease_in_out(time: float, duration: float, overshoot_or_amplitude: float, period: float) -> float:
        return _evaluate_builtin_ease(35, time, duration, overshoot_or_amplitude, period)


def _factory_ease_kind(ease):
    return (Ease.OUT_QUAD if ease in (Ease.INTERNAL_ZERO, Ease.INTERNAL_CUSTOM) else ease).value


@overload
def stop_motion(
    motion_fps: int, ease: Ease | None = None
) -> Callable[[float, float, float, float], float]: ...
@overload
def stop_motion(
    motion_fps: int, anim_curve: AnimationCurve
) -> Callable[[float, float, float, float], float]: ...
@overload
def stop_motion(
    motion_fps: int, custom_ease: Callable[[float, float, float, float], float]
) -> Callable[[float, float, float, float], float]: ...
def stop_motion(motion_fps, ease=None, *, anim_curve=None, custom_ease=None):
    if sum(value is not None for value in (ease, anim_curve, custom_ease)) > 1:
        raise TypeError("provide one ease, anim_curve or custom_ease")
    from .core import _default_manager
    from .curve import EaseCurve

    source = next(
        (value for value in (ease, anim_curve, custom_ease) if value is not None),
        _default_manager.default_ease_type,
    )
    if isinstance(source, Ease):
        return partial(_StopMotionClock(motion_fps).evaluate_builtin, _factory_ease_kind(source))
    elif isinstance(source, AnimationCurve):
        source = EaseCurve(source).evaluate
    elif isinstance(source, EaseCurve):
        source = source.evaluate
    elif not callable(source):
        raise TypeError("ease must be Ease, AnimationCurve or a four-argument function")
    return partial(_StopMotionClock(motion_fps).evaluate, source)


class EaseFactory:
    stop_motion = staticmethod(stop_motion)


def resolve_ease(ease, overshoot_or_amplitude=1.70158, period=0.0, duration=None):
    from .curve import EaseCurve

    if isinstance(ease, AnimationCurve):
        return EaseCurve(ease)
    if isinstance(ease, EaseCurve):
        return ease
    if isinstance(ease, _EaseKernel):
        if duration is None:
            return ease
        def compiled(t):
            return ease.sample(t, duration())
        compiled._native_kernel = ease
        return compiled
    if callable(ease):
        clock = duration or (lambda: 1.0)
        arguments = (ease, clock, overshoot_or_amplitude, period)
        sample = partial(_sample_custom_ease, arguments)
        sample._time_arguments = arguments
        return sample
    if not isinstance(ease, Ease):
        raise TypeError("ease must be Ease, AnimationCurve or a four-argument function")
    if ease == Ease.INTERNAL_CUSTOM:
        def missing_custom(t):
            raise TypeError("INTERNAL_CUSTOM requires a custom ease function")
        return missing_custom
    kernel = _compile_builtin(ease, overshoot_or_amplitude, period)
    if period and ease in (Ease.IN_ELASTIC, Ease.OUT_ELASTIC, Ease.IN_OUT_ELASTIC) and duration is not None:
        def dynamic_duration(t):
            return kernel.sample(t, duration())
        dynamic_duration._native_kernel = kernel
        return dynamic_duration
    return kernel


@lru_cache(maxsize=256)
def _compile_builtin(ease, amplitude=1.70158, period=0.0):
    return _EaseKernel(ease.value, amplitude, period)


def native_ease_kernel(sampler):
    """Select the numerical route once when the public ease configuration changes."""
    return sampler if isinstance(sampler, _EaseKernel) else getattr(sampler, "_native_kernel", None)


def time_ease_sampler(sampler, kernel, source, arguments):
    """Bind the resolved ease to explicit elapsed/duration arguments."""
    if kernel is not None:
        return kernel.evaluate
    from .curve import EaseCurve
    if isinstance(sampler, EaseCurve):
        return sampler.evaluate
    return partial(_evaluate_custom_ease, source, *arguments)


class EaseManager:
    """Public ease utility used by custom plugins, sharing the runtime sampler."""

    @staticmethod
    @overload
    def evaluate(t: "Tween", time: float, duration: float, overshoot_or_amplitude: float, period: float) -> float: ...
    @staticmethod
    @overload
    def evaluate(ease_type: Ease, custom_ease: Callable[[float, float, float, float], float] | None,
                 time: float, duration: float, overshoot_or_amplitude: float, period: float) -> float: ...
    @staticmethod
    def evaluate(*args, **kwargs):
        from .core import Tween, _bind_arguments
        from .curve import EaseCurve

        tween_overload = "t" in kwargs or args and isinstance(args[0], Tween)
        tail = ("time", "duration", "overshoot_or_amplitude", "period")
        if tween_overload:
            tween, time, duration, amplitude, period = _bind_arguments(
                ("t", *tail), args, kwargs
            )
            source = (
                Ease.INTERNAL_ZERO
                if tween._initialized and tween._duration <= 0
                else tween._ease_source
            )
            if isinstance(source, AnimationCurve):
                source = tween._ease
        else:
            source, custom, time, duration, amplitude, period = _bind_arguments(
                ("ease_type", "custom_ease", *tail), args, kwargs
            )
            if source == Ease.INTERNAL_CUSTOM:
                if custom is None:
                    raise TypeError("INTERNAL_CUSTOM requires a custom ease function")
                return _evaluate_custom_ease(custom, amplitude, period, time, duration)
        if isinstance(source, AnimationCurve):
            return EaseCurve(source).evaluate(time, duration, amplitude, period)
        if isinstance(source, EaseCurve):
            return source.evaluate(time, duration, amplitude, period)
        if isinstance(source, _EaseKernel):
            return source.evaluate(time, duration)
        if callable(source):
            return _evaluate_custom_ease(source, amplitude, period, time, duration)
        if not isinstance(source, Ease):
            raise TypeError("ease must be Ease, AnimationCurve or a four-argument function")
        return _evaluate_builtin_ease(source.value, time, duration, amplitude, period)

    @staticmethod
    def evaluate_unclamped(t, time, duration, overshoot_or_amplitude, period):
        """Sample an ease with the reference custom-plugin loop offsets."""
        from .core import LoopType

        value = EaseManager.evaluate(t, time, duration, overshoot_or_amplitude, period)
        incremental = t.loop_type == LoopType.INCREMENTAL
        if incremental:
            value += t.completed_loops() - int(t.is_complete())
        parent = t._parent
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            value += (t._loops if incremental else 1) * (parent.completed_loops() - int(parent.is_complete()))
        return value

    @staticmethod
    def compile(ease: Ease, overshoot_or_amplitude: float = 1.70158, period: float = 0.0):
        """Compile a built-in ease; large buffer jobs release the GIL once."""
        if not isinstance(ease, Ease) or ease == Ease.INTERNAL_CUSTOM:
            raise TypeError("compile requires a built-in Ease")
        return _compile_builtin(ease, overshoot_or_amplitude, period)

    @staticmethod
    def to_ease_function(ease):
        if not isinstance(ease, Ease):
            raise TypeError("ease must be Ease")
        return partial(_evaluate_builtin_ease, _factory_ease_kind(ease))
