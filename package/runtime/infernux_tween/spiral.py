"""Spiral interpolation on the same plugin, state and pooling path as custom tweens."""

from enum import Enum
from math import copysign, cos, inf, isfinite, nan, sin
from typing import overload

from infernux.lib import Vector3, quatf

from .core import LoopType, _f32
from .plugin import AbsTweenPlugin, _from_arguments
from .rotation import _rotate_offset


class SpiralMode(Enum):
    EXPAND = 0
    EXPAND_THEN_CONTRACT = 1


def _divide(numerator, denominator):
    """C# float division preserves invalid/zero cases instead of raising."""
    if denominator == 0:
        return nan if numerator == 0 else copysign(inf, numerator * copysign(1, denominator))
    return _f32(numerator / denominator)


class SpiralOptions:
    def __init__(self):
        self.reset()

    def reset(self):
        self.depth = self.frequency = self.speed = 0.0
        self.mode, self.snapping = SpiralMode.EXPAND, False
        self._unit, self._axis_q = 0.0, quatf(0, 0, 0, 0)


class _DefaultDirection:
    def __get__(self, instance, owner):
        return Vector3(0, 0, 1)

    def __set__(self, instance, value):
        raise AttributeError("default_direction is read-only")


class SpiralPlugin(AbsTweenPlugin[Vector3, Vector3, SpiralOptions]):
    storage_default = staticmethod(lambda: Vector3(0, 0, 0))
    default_direction = _DefaultDirection()
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self, t):
        pass

    @overload
    def set_from(self, t, is_relative: bool): ...
    @overload
    def set_from(self, t, from_value, set_immediately: bool, is_relative: bool): ...
    def set_from(self, t, *args, **kwargs):
        if kwargs:
            args = _from_arguments(args, kwargs)
        # The reference plugin deliberately does not implement From.
        if len(args) == 1 and type(args[0]) is bool:
            return
        if len(args) == 3 and isinstance(args[0], Vector3) and all(type(flag) is bool for flag in args[1:]):
            return
        raise TypeError("set_from expects is_relative, or Vector3/set_immediately/is_relative")

    def convert_to_start_value(self, t, value):
        return Vector3(*value)

    def set_relative_end_value(self, t):
        pass

    def set_change_value(self, t):
        options = t.plug_options
        options.speed = _divide(_f32(options.speed * 10), options.frequency)
        options._axis_q = quatf.look_rotation(t.end_value)

    def get_speed_based_duration(self, options, units_x_second, change_value):
        return units_x_second

    def evaluate_and_apply(self, options, t, is_relative, getter, setter, elapsed,
                           start_value, change_value, duration, using_inverse_position,
                           new_completed_steps, update_notice):
        progress = 1.0 if duration == 0 else _f32(t._ease(_divide(_f32(elapsed), _f32(duration))))
        increment = t.completed_loops() - int(t.is_complete()) if t.loop_type == LoopType.INCREMENTAL else 0
        if options.mode == SpiralMode.EXPAND:
            progress = _f32(progress + increment)
            distance = _f32(_f32(duration * progress) * options.speed)
            radius = distance
            angle = _f32(distance * options.frequency)
        else:
            # Contract repeats the angular phase while incremental loops scale
            # the envelope. Completion uses the reference's distinct last cycle.
            scale = t.completed_loops() + 1 - 2 * int(t.is_complete()) if t.loop_type == LoopType.INCREMENTAL else 1
            distance = _f32(_f32(duration * progress) * options.speed)
            radius = _f32(_f32(duration * _f32(1 - progress)) * options.speed) if progress > .5 else distance
            radius = _f32(radius * scale)
            angle = _f32(distance * options.frequency) if scale else nan
            progress = _f32(progress * scale)
        if isfinite(angle):
            value = Vector3(_f32(_f32(cos(angle)) * radius), _f32(_f32(sin(angle)) * radius), _f32(options.depth * progress))
            value = start_value + _rotate_offset(options._axis_q, value)
        else:
            value = Vector3(0, 0, 0) * nan
        if options.snapping and all(isfinite(component) for component in value):
            value = Vector3(*(round(component) for component in value))
        setter(value)
