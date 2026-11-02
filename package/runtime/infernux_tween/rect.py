"""Rect values retain their type while sharing the common playback engine."""
from math import sqrt
from typing import overload

from infernux.screen import Rect, RectOffset
from infernux.lib._Infernux import _RectTweenSnapshot, _RectOffsetInterpolation, _rect_offset_speed

from .core import LoopType, TweenerCore, _FloatTweener, _UNSET, _f32
from .plugin import AbsTweenPlugin, NoOptions, _PluginTweenerCore, _from_arguments


def switch_to_rect_transform(source, target):
    """Return target's anchored position that aligns the two rectangle centres.

    Positions are projected onto the target's rectangle plane along screen Z.
    The source centre offset uses unrotated screen coordinates. This is a
    coordinate conversion only: neither rectangle's authored pose is changed.
    """
    from infernux.lib import Vector2, Vector3
    from infernux.ui._rect_transform import bind_rect
    from .core import _f32

    source_layout, target_layout = bind_rect(source), bind_rect(target)
    source_rect, target_rect = source_layout.rect, target_layout.rect
    source_pivot, target_pivot = source_layout.pivot, target_layout.pivot
    source_units, target_units = source_layout._position_scale, target_layout._position_scale
    position = source.transform.position
    origin = Vector3(
        _f32(position.x + _f32(source_rect.z * _f32(.5 - source_pivot.x)) * source_units),
        _f32(position.y + _f32(source_rect.w * _f32(.5 - source_pivot.y)) * source_units),
        -100.,
    )
    normal = target.transform.rotation * Vector3(0, 0, -1)
    magnitude = _f32(sqrt(_f32(normal.x*normal.x + normal.y*normal.y + normal.z*normal.z)))
    normal = Vector3(normal.x / magnitude, normal.y / magnitude, normal.z / magnitude)
    plane_position = target.transform.position
    distance = -_f32(normal.x*plane_position.x + normal.y*plane_position.y + normal.z*plane_position.z)
    origin_distance = _f32(normal.x*origin.x + normal.y*origin.y + normal.z*origin.z)
    local = Vector2(0, 0)
    if normal.z != 0:
        travel = _f32((-origin_distance - distance) / normal.z)
        if travel > 0:
            origin.z = _f32(origin.z + travel)
            point = target.transform.inverse_transform_point(origin)
            local = Vector2(point.x / target_units, point.y / target_units)
    offset = Vector2(
        _f32(target_rect.z * _f32(target_pivot.x - .5)),
        _f32(target_rect.w * _f32(target_pivot.y - .5)),
    )
    return target_layout.anchored_position + local + offset


def _components(value):
    if isinstance(value, Rect):
        return value.x, value.y, value.width, value.height
    values = tuple(value)
    if len(values) != 4:
        raise ValueError("Rect tween values require four components")
    return values


def _rect(value):
    return Rect(*(_f32(v) for v in _components(value)))


class RectTweener(TweenerCore):
    _core_plugin_kind = 'rect'
    set_options = _FloatTweener.set_options
    _copy_argument = staticmethod(_rect)

    def __init__(self, getter, setter, end_value, duration):
        super().__init__(getter, setter, _rect(end_value), duration)

    def _read_startup_value(self):
        if self._from and not self._from_relative and self._from_value is not _UNSET:
            return self._from_value
        return super()._read_startup_value()

    def _storage_default(self):
        return Rect(0., 0., 0., 0.)

    @TweenerCore.start_value.setter
    def start_value(self, value):
        TweenerCore.start_value.fset(self, _rect(value))

    @TweenerCore.end_value.setter
    def end_value(self, value):
        self._end = _rect(value)

    @TweenerCore.change_value.setter
    def change_value(self, value):
        TweenerCore.change_value.fset(self, _rect(value))

    def _convert_start_value(self, value):
        return _rect(value)

    def _set_values(self, start, end):
        self._start, self._end = _rect(start), _rect(end)
        self._delta = Rect(*(_f32(b - a) for a, b in zip(self._start, self._end)))
        self._compile_numeric_value()

    def _compile_numeric_value(self):
        self._numeric_value = _RectTweenSnapshot(tuple(self._start), tuple(self._delta), self._snapping)
        self._numeric_rounding = True
        self._bind_numeric_sampler()

    def _apply(self, progress, cycle, previous, callbacks):
        setter = self._setter
        own = self._incremental_cycles(cycle, False)
        parent = self._parent
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            value = self._sample_parent_incremental(progress, own, parent)
        elif self._sample_numeric is not None:
            value = self._sample_numeric(progress, own)
        else:
            value = self._interpolate_numeric(self._ease(progress), own)
        setter(Rect(*value))

    def _relative_value(self, current, value):
        return Rect(*(_f32(a + b) for a, b in zip(current, value)))

    def _distance(self):
        # Rect speed is the size diagonal; moving its origin does not
        # contribute to speed-based duration.
        return sqrt(self._delta[2]**2+self._delta[3]**2)


_EDGES = ("left", "right", "top", "bottom")


_offset_interpolation = _RectOffsetInterpolation()


def _offset_values(value):
    return value.left, value.right, value.top, value.bottom


def _apply_offset(t, setter, elapsed, start, change, duration):
    own = t.completed_loops() - int(t.is_complete()) if t.loop_type == LoopType.INCREMENTAL else 0
    parent, multiplier, parent_iterations = t._parent, 1, 0
    if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
        multiplier = t._loops if t.loop_type == LoopType.INCREMENTAL else 1
        parent_iterations = parent.completed_loops() - int(parent.is_complete())
    first, delta = _offset_values(start), _offset_values(change)
    if t._numeric_ease is not None:
        value = _offset_interpolation.sample(first, delta, own, multiplier, parent_iterations,
                                              t._numeric_ease, elapsed, duration)
    else:
        _offset_interpolation.prepare(first, delta, own, multiplier, parent_iterations)
        factor = t._ease_time(elapsed, duration)
        value = _offset_interpolation.interpolate(_offset_values(change), factor)
    setter(RectOffset._from_int32(value))


class RectOffsetTweener(_PluginTweenerCore):
    """Typed offset lifecycle with direct built-in numerical sampling."""

    def __init__(self, getter, setter, end_value, duration, plugin=None):
        super().__init__(_offset_plugin if plugin is None else plugin, getter, setter, end_value, duration)

    def _apply(self, progress, cycle, previous, callbacks):
        _apply_offset(self, self._setter, progress * self._duration, self._start, self._delta, self._duration)


class RectOffsetPlugin(AbsTweenPlugin[RectOffset, RectOffset, NoOptions]):
    """Reference-object edge storage on the shared custom-plugin lifecycle."""

    def reset(self, t):
        t.start_value = t.end_value = t.change_value = None

    def convert_to_start_value(self, t, value):
        return RectOffset._from_int32(_offset_values(value))

    @staticmethod
    def _add(first, second):
        for edge in _EDGES:
            value = getattr(first, edge) + getattr(second, edge)
            setattr(second, edge, ((value + 2**31) & 0xffffffff) - 2**31)
        return second

    @overload
    def set_from(self, t, is_relative: bool): ...
    @overload
    def set_from(self, t, from_value, set_immediately: bool, is_relative: bool): ...
    def set_from(self, t, *args, **kwargs):
        if kwargs:
            args = _from_arguments(args, kwargs)
        current = self.convert_to_start_value(t, t.getter())
        if len(args) == 1:
            relative, = args
            t.start_value, t.end_value = t.end_value, current
            if relative:
                self._add(current, t.start_value)
            immediate = True
        else:
            start, immediate, relative = args
            t.start_value = start
            if relative:
                self._add(current, t.start_value)
                self._add(current, t.end_value)
        if immediate:
            t.setter(t.start_value)

    def set_relative_end_value(self, t):
        self._add(t.start_value, t.end_value)

    def set_change_value(self, t):
        t.change_value = RectOffset._from_int32(tuple(((getattr(t.end_value, edge) - getattr(t.start_value, edge)
                                                      + 2**31) & 0xffffffff) - 2**31 for edge in _EDGES))

    def get_speed_based_duration(self, options, units_x_second, change_value):
        return _rect_offset_speed(_offset_values(change_value), units_x_second)

    def evaluate_and_apply(self, options, t, is_relative, getter, setter, elapsed,
                           start_value, change_value, duration, using_inverse_position,
                           new_completed_steps, update_notice):
        _apply_offset(t, setter, elapsed, start_value, change_value, duration)


_offset_plugin = RectOffsetPlugin()
