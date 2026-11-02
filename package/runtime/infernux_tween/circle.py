"""Circle interpolation on the shared typed plugin lifecycle and native kernel."""
from math import atan2
from typing import overload

from infernux.lib import Vector2
from infernux.lib._Infernux import _CircleGeometry, _tween_point_on_circle

from .core import LoopType, _bind_arguments, _f32
from .plugin import AbsTweenPlugin, _PluginTweenerCore

_ZERO_GEOMETRY = _CircleGeometry((0, 0), 0)


class TweenUtils:
    """Small geometry utilities shared with native circle interpolation."""

    get_point_on_circle = staticmethod(_tween_point_on_circle)


class CircleOptions:
    def __init__(self):
        self._geometry = _ZERO_GEOMETRY
        self.reset()

    @property
    def end_value_degrees(self):
        return self._end_value_degrees

    @end_value_degrees.setter
    def end_value_degrees(self, value):
        self._end_value_degrees = _f32(value)

    def reset(self):
        self._initialized = False
        self._start_value_degrees = self.end_value_degrees = 0.0
        self.relative_center = self.snapping = False

    def initialize(self, start_value: Vector2, end_value: Vector2):
        self._initialized = True
        center = start_value + end_value if self.relative_center else end_value
        offset = start_value - center
        self._start_value_degrees = _f32(_f32(atan2(offset.x, offset.y)) * _f32(57.29577951308232))
        self._geometry = _CircleGeometry(tuple(center), offset.magnitude)


class CirclePlugin(AbsTweenPlugin[Vector2, Vector2, CircleOptions]):
    storage_default = staticmethod(lambda: Vector2(0, 0))
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
        implicit = (len(args) == 1 and not kwargs) or (not args and set(kwargs) == {'is_relative'})
        if implicit:
            relative, = _bind_arguments(('is_relative',), args, kwargs)
        else:
            value, immediate, relative = _bind_arguments(('from_value', 'set_immediately', 'is_relative'), args, kwargs)
            degrees = value.x
        options = t.plug_options
        if not options._initialized:
            t.start_value = t.getter()
            options.initialize(t.start_value, t.end_value)
        if implicit:
            previous = options.end_value_degrees
            options.end_value_degrees = options._start_value_degrees
            options._start_value_degrees = _f32(options.end_value_degrees + previous) if relative else previous
            start = self.get_position_on_circle(options, options._start_value_degrees)
            t.start_value = start
            t.setter(start)
        else:
            if relative:
                options.end_value_degrees = options.end_value_degrees + options._start_value_degrees
                degrees = _f32(degrees + options._start_value_degrees)
            options._start_value_degrees = degrees
            start = self.get_position_on_circle(options, degrees)
            t.start_value = start
            if immediate:
                t.setter(start)

    def convert_to_start_value(self, t, value):
        return Vector2(*value)

    def set_relative_end_value(self, t):
        options = t.plug_options
        if not options._initialized:
            options.initialize(t.start_value, t.end_value)
        options.end_value_degrees = options.end_value_degrees + options._start_value_degrees

    def set_change_value(self, t):
        options = t.plug_options
        if not options._initialized:
            options.initialize(t.start_value, t.end_value)
        t.change_value = Vector2(_f32(options.end_value_degrees - options._start_value_degrees), 0)

    def get_speed_based_duration(self, options, units_x_second, change_value):
        return _f32(change_value.x / units_x_second)

    def get_position_on_circle(self, options, degrees):
        return options._geometry.position(degrees, options.snapping)

    @staticmethod
    def _sample(tween, progress, cycle):
        options = tween.plug_options
        geometry, start, change, snapping = options._geometry, options._start_value_degrees, tween.change_value.x, options.snapping
        own = tween._incremental_cycles(cycle, False)
        parent, parent_increment, parent_multiplier = tween._parent, 0, 1
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            parent_cycle = parent._sample_context[0] if parent._sample_context else parent._sample_cycle
            parent_increment = parent._incremental_cycles(parent_cycle, False)
            parent_multiplier = tween._loops if tween.loop_type == LoopType.INCREMENTAL else 1
        if tween._numeric_ease is not None:
            return geometry.sample(progress, tween._duration, tween._numeric_ease,
                start, change, own, parent_multiplier, parent_increment, snapping)
        return geometry.interpolate(start, change, tween._ease(progress), own, parent_multiplier, parent_increment, snapping)

    def evaluate_and_apply(self, options, t, is_relative, getter, setter, elapsed,
                           start_value, change_value, duration, using_inverse_position,
                           new_completed_steps, update_notice):
        geometry, start, change, snapping = options._geometry, options._start_value_degrees, change_value.x, options.snapping
        own = t._incremental_cycles(0, False)
        parent, parent_increment, parent_multiplier = t._parent, 0, 1
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            parent_cycle = parent._sample_context[0] if parent._sample_context else parent._sample_cycle
            parent_increment = parent._incremental_cycles(parent_cycle, False)
            parent_multiplier = t._loops if t.loop_type == LoopType.INCREMENTAL else 1
        if t._numeric_ease is not None:
            value = geometry.sample(elapsed / duration if duration else 1, duration, t._numeric_ease,
                                    start, change, own, parent_multiplier, parent_increment, snapping)
        else:
            value = geometry.interpolate(start, change, t._ease_time(elapsed, duration),
                                         own, parent_multiplier, parent_increment, snapping)
        setter(value)


class CircleTweener(_PluginTweenerCore):
    _from_value_keyword = 'from_value_degrees'
    @staticmethod
    def _copy_argument(value):
        return value if type(value) in (int, float) else Vector2(*value)

    def __init__(self, plugin, getter, setter, end_value, duration):
        super().__init__(plugin, getter, setter, Vector2(*end_value), duration)
        if type(plugin) is not CirclePlugin:
            # Derived plugins retain the normal virtual callback path.
            self._apply = super()._apply

    def set_options(self, end_value_degrees: float, relative_center: bool=True, snapping: bool=False):
        if self._active:
            options = self.plug_options
            options.end_value_degrees = end_value_degrees
            options.relative_center, options.snapping = relative_center, snapping
        return self

    def _apply_from(self, from_value, set_immediately, relative):
        if type(from_value) in (int, float):
            from_value = Vector2(from_value, 0)
        return super()._apply_from(from_value, set_immediately, relative)

    def _apply(self, progress, cycle, previous, callbacks):
        self._setter(CirclePlugin._sample(self, progress, cycle))
