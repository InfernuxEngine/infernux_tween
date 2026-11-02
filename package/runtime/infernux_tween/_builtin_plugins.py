"""Public built-in plugin state; normal playback keeps its native fast path."""

from math import sqrt
from typing import overload
import numpy as np

from infernux.lib import Vector2, Vector3, vec4f, quatf
from infernux.screen import Rect
from infernux.lib._Infernux import (
    _ScalarTweenSnapshot, _Float32TweenSnapshot, _SignedIntegerTweenSnapshot, _UInt32TweenSnapshot, _UInt64TweenSnapshot, _ColorTweenSnapshot,
    _Vector2TweenSnapshot, _Vector3TweenSnapshot, _Vector4TweenSnapshot, _RectTweenSnapshot,
    _round_tween_value,
)

from .core import AxisConstraint, LoopType, _bind_arguments, _f32
from .plugin import AbsTweenPlugin, NoOptions, _from_arguments


def _option_field(name, storage):
    def read(self):
        owner = self._owner
        return self._values[name] if owner is None else getattr(owner, storage)

    def write(self, value):
        owner = self._owner
        if owner is None:
            self._values[name] = value
        else:
            setattr(owner, storage, value)
            owner._core_option_changed(storage)

    return property(read, write)


class _Options:
    _fields = ()
    _defaults = ()

    def __init__(self):
        self._owner = None
        self._values = dict(self._defaults)

    def __copy__(self):
        result = type(self)()
        result._values = {field: getattr(self, field) for field, _ in self._fields}
        return result

    def reset(self):
        for field, value in self._defaults:
            setattr(self, field, value)


class FloatOptions(_Options):
    _fields = (('snapping', '_snapping'),)
    _defaults = (('snapping', False),)
    snapping = _option_field('snapping', '_snapping')


class RectOptions(FloatOptions):
    pass


class VectorOptions(_Options):
    _fields = (('axis_constraint', '_constraint'), ('snapping', '_snapping'))
    _defaults = (('axis_constraint', AxisConstraint.NONE), ('snapping', False))
    axis_constraint = _option_field('axis_constraint', '_constraint')
    snapping = _option_field('snapping', '_snapping')


class Vector3ArrayOptions(VectorOptions):
    _fields = VectorOptions._fields + (('_durations', '_durations'),)
    _defaults = VectorOptions._defaults + (('_durations', None),)
    _durations = _option_field('_durations', '_durations')


class ColorOptions(_Options):
    _fields = (('alpha_only', '_alpha_only'),)
    _defaults = (('alpha_only', False),)
    alpha_only = _option_field('alpha_only', '_alpha_only')


class UintOptions(_Options):
    _fields = (('is_negative_change_value', '_negative_change'),)
    _defaults = (('is_negative_change_value', False),)
    is_negative_change_value = _option_field('is_negative_change_value', '_negative_change')


_VECTOR_SNAPSHOTS = {Vector2: _Vector2TweenSnapshot, Vector3: _Vector3TweenSnapshot, vec4f: _Vector4TweenSnapshot}


class _BuiltinPlugin(AbsTweenPlugin):
    def __init__(self, kind, value_type, bits=0):
        self.kind = kind
        self.value_type = self.storage_type = value_type
        self.bits = bits
        self.options_type = (RectOptions if kind == 'rect'
                             else UintOptions if kind == 'unsigned' and bits == 32
                             else FloatOptions if value_type is np.float32
                             else NoOptions if kind in ('scalar','unsigned')
                             else ColorOptions if kind == 'color' else VectorOptions)
        if kind == 'string':
            from .string import StringOptions
            self.options_type = StringOptions
        elif kind == 'array':
            from .array import Vector3Array
            self.value_type, self.storage_type = Vector3, Vector3Array
            self.options_type = Vector3ArrayOptions
        elif kind == 'euler':
            from .rotation import QuaternionOptions
            self.value_type, self.storage_type = quatf, Vector3
            self.options_type = QuaternionOptions
        self._interpolate_name = {np.int32: 'interpolate_int32', np.int64: 'interpolate_int64',
                                  np.float64: 'interpolate_float64'}.get(value_type, 'interpolate')

    def storage_default(self):
        if self.kind in ('string', 'array'):
            return None
        if self.kind == 'rect':
            return Rect(0., 0., 0., 0.)
        return [0., 0., 0., 0.] if self.kind == 'color' else self.storage_type()

    def reset(self, t):
        if self.kind == 'string':
            t.start_value = t.end_value = t.change_value = ''
        elif self.kind == 'array':
            t._segment_starts = t._segment_changes = t._end_values = None
            t._numeric_segments = t._sample_segments = None

    def convert_to_start_value(self, t, value):
        if self.kind == 'euler':
            return value.euler_angles
        if self.kind == 'array':
            return self.storage_type([value, *list(t.end_value)[:-1]])
        if self.kind == 'string':
            return value
        if self.kind == 'rect':
            return Rect(*(_f32(v) for v in value))
        if self.kind == 'color':
            return [_f32(v) for v in value]
        if self.kind == 'vector':
            return self.storage_type(value) if self.storage_type in (tuple, list) else self.storage_type(*value)
        return self.storage_type(value)

    def _add(self, first, second):
        if self.kind == 'rect':
            return Rect(*(_f32(a + b) for a, b in zip(first, second)))
        if self.kind == 'color':
            return [_f32(a + b) for a, b in zip(first, second)]
        if self.storage_type in (tuple, list):
            return self.storage_type(a + b for a, b in zip(first, second))
        if self.bits:
            value = (int(first) + int(second)) & ((1 << self.bits) - 1)
            if self.kind == 'scalar' and value >= 1 << (self.bits - 1): value -= 1 << self.bits
            return self.storage_type(value)
        return first + second

    @overload
    def set_from(self, t, is_relative: bool): ...
    @overload
    def set_from(self, t, from_value, set_immediately: bool, is_relative: bool): ...
    def set_from(self, t, *args, **kwargs):
        if kwargs:
            args = _from_arguments(args, kwargs)
        if self.kind == 'euler':
            from .rotation import _set_euler_from
            return _set_euler_from(t, *args)
        if self.kind == 'array':
            return
        current = self.convert_to_start_value(t, t.getter())
        if self.kind == 'string':
            if len(args) == 1:
                t.start_value, t.end_value = t.end_value, current
                immediate = True
            else:
                start, immediate, relative = _bind_arguments(
                    ('from_value', 'set_immediately', 'is_relative'), args, {})
                t.start_value = (start or '') + (current or '') if relative else start
            if immediate:
                t.setter(t.start_value)
            return
        if len(args) == 1:
            relative, = args
            t.start_value, t.end_value = t.end_value, current
            if relative:
                t.start_value = self._add(current, t.start_value)
            immediate = True
        else:
            start, immediate, relative = _bind_arguments(
                ('from_value', 'set_immediately', 'is_relative'), args, {})
            t.start_value = self.convert_to_start_value(t, start)
            if relative:
                t.start_value = self._add(current, t.start_value)
                t.end_value = self._add(current, t.end_value)
        if immediate:
            options = t.plug_options
            t.setter(self._compose(t.start_value, t.getter,
                options.axis_constraint if self.kind == 'vector' else 0,
                options.alpha_only if self.kind == 'color' else False))

    def set_relative_end_value(self, t):
        if self.kind == 'array':
            start, end = t.start_value, t.end_value
            for index in range(len(end)):
                if index:
                    start[index] = end[index - 1]
                end[index] = end[index] + start[index]
            return
        if self.kind == 'string':
            return
        start, end = t.start_value, t.end_value
        t.end_value = ([*start[:3], _f32(start[3] + end[3])]
                           if self.kind == 'color' and t.plug_options.alpha_only
                           else self._add(start, end))

    def set_change_value(self, t):
        start, end, options = t.start_value, t.end_value, t.plug_options
        if self.kind == 'string':
            from infernux.lib._Infernux import _StringTweenSnapshot
            snapshot = _StringTweenSnapshot(start, end)
            options._start_value_stripped_length = snapshot.start_length(True)
            options._change_value_stripped_length = snapshot.length(True)
            change = end
        elif self.kind == 'euler':
            from .rotation import _euler_tween_change
            change = _euler_tween_change(start, end, options.rotate_mode.value, t._relative)
        elif self.kind == 'array':
            change = self.storage_type(b - a for a, b in zip(start, end))
        elif self.kind == 'color':
            change = [_f32(_f32(b) - _f32(a)) for a, b in zip(start, end)]
        elif self.kind == 'rect':
            change = Rect(*(_f32(b - a) for a, b in zip(start, end)))
        elif self.kind == 'vector':
            values = [b - a for a, b in zip(start, end)]
            if options.axis_constraint in tuple(2 << i for i in range(len(values))):
                values = [v if options.axis_constraint == 2 << i else 0 for i, v in enumerate(values)]
            change = self.storage_type(values) if self.storage_type in (tuple, list) else self.storage_type(*values)
        elif self.kind == 'unsigned':
            if self.bits == 32:
                options.is_negative_change_value = end < start
                change = abs(int(end) - int(start))
            else:
                change = (int(end) - int(start)) & ((1 << 64) - 1)
        else:
            change = int(end) - int(start) if self.bits else end - start
            if self.bits:
                change = (change + (1 << (self.bits - 1))) % (1 << self.bits) - (1 << (self.bits - 1))
        t.change_value = change

    def get_speed_based_duration(self, options, units_x_second, change_value):
        if self.kind == 'euler':
            from infernux.lib._Infernux import _euler_tween_speed
            return _euler_tween_speed(change_value, units_x_second)
        if self.kind == 'array':
            from infernux.lib._Infernux import _tween_array_duration, _tween_segment_speed_durations
            values = _tween_segment_speed_durations(change_value, options._durations)
            options._durations[:] = values
            return _tween_array_duration(values)
        if self.kind == 'string':
            from infernux.lib._Infernux import _StringTweenSnapshot
            length = (options._change_value_stripped_length if options.rich_text_enabled
                      else _StringTweenSnapshot('', change_value).length(False))
            return length / units_x_second
        distance = (sqrt(change_value.width**2 + change_value.height**2) if self.kind == 'rect'
                    else 1. if self.kind == 'color' else abs(int(change_value)) if self.bits
                    else abs(change_value) if self.kind == 'scalar'
                    else sqrt(sum(v * v for v in change_value)))
        return distance / units_x_second

    def _compose(self, value, getter, constraint=0, alpha_only=False):
        if self.kind == 'color' and alpha_only:
            return [*getter()[:3], value[3]]
        if self.kind == 'vector' and constraint in tuple(2 << i for i in range(len(value))):
            current = getter()
            values = [v if constraint & (2 << i) else current[i] for i, v in enumerate(value)]
            return self.storage_type(values) if self.storage_type in (tuple, list) else self.storage_type(*values)
        return value

    def evaluate_and_apply(self, options, t, is_relative, getter, setter, elapsed,
                           start_value, change_value, duration, using_inverse_position,
                           new_completed_steps, update_notice):
        own = t.completed_loops() - int(t.is_complete()) if t.loop_type == LoopType.INCREMENTAL else 0
        parent = t._parent
        offset = (parent.completed_loops() - int(parent.is_complete())
                  if parent is not None and parent.loop_type == LoopType.INCREMENTAL else 0)
        multiplier = t._loops if t.loop_type == LoopType.INCREMENTAL else 1
        constraint = options.axis_constraint if self.kind in ('vector', 'array') else 0
        alpha_only = options.alpha_only if self.kind == 'color' else False
        if self.kind == 'array':
            from infernux.lib._Infernux import _TweenLiveSegments
            snapping = options.snapping
            plan = _TweenLiveSegments(start_value, change_value, options._durations)
            if duration == 0:
                value = plan.interpolate(0, 1., own + multiplier * offset)
            elif t._numeric_ease is not None:
                value = plan.sample_time(elapsed, duration, t._numeric_ease, own + multiplier * offset)
            else:
                segment = plan.locate_time(elapsed, duration)
                factor = t._ease_time(segment.progress * segment.width, segment.width) if segment.width else 1.
                value = plan.interpolate(segment.index, factor, own + multiplier * offset)
            constraint = int(constraint) if constraint in (2, 4, 8) else 0
            if constraint:
                current = getter()
                value = Vector3(*(v if constraint & (2 << i) else current[i] for i, v in enumerate(value)))
            setter(_round_tween_value(value, constraint) if snapping else value)
            return
        if self.kind == 'euler':
            from .rotation import _EulerTweenSnapshot
            change = t.change_value if options.dynamic_look_at else change_value
            recipe = _EulerTweenSnapshot(start_value, change, t.end_value, options.up,
                options.dynamic_look_at_world_position, options.rotate_mode.value, int(options.axis_constraint), is_relative)
            if options.dynamic_look_at:
                recipe.prepare_look_at(t.target.position)
            setter(recipe.sample_custom_time(t._ease_time, elapsed, duration, own, multiplier, offset))
            return
        if self.kind == 'string':
            from infernux.lib._Infernux import _StringTweenSnapshot
            from .string import _LINEAR
            chars = options.scrambled_chars
            plan = _StringTweenSnapshot(start_value, change_value).bind(_LINEAR, duration,
                options.rich_text_enabled, is_relative, options.scramble_mode.value,
                chars._alphabet if chars is not None else None,
                options._start_value_stripped_length, options._change_value_stripped_length)
            setter(plan.interpolate(t._ease_time(elapsed, duration), own))
            return
        elif self.kind == 'unsigned':
            snapshot = (_UInt32TweenSnapshot(int(start_value), int(change_value), options.is_negative_change_value)
                        if self.bits == 32 else _UInt64TweenSnapshot(int(start_value), int(change_value)))
        elif self.bits:
            snapshot = _SignedIntegerTweenSnapshot(int(start_value), int(start_value) + int(change_value), self.bits)
        elif self.kind == 'scalar':
            snapshot = (_Float32TweenSnapshot(start_value, change_value, options.snapping)
                        if self.storage_type is np.float32 else _ScalarTweenSnapshot(start_value, change_value, t._snapping))
        elif self.kind == 'color':
            snapshot = _ColorTweenSnapshot(start_value, change_value)
        elif self.kind == 'rect':
            snapshot = _RectTweenSnapshot(tuple(start_value), tuple(change_value), options.snapping)
        else:
            constructor = _VECTOR_SNAPSHOTS.get(self.storage_type)
            if constructor is None:
                first, change, snapping = tuple(start_value), tuple(change_value), options.snapping
                factor = t._ease_time(elapsed, duration)
                value = self.storage_type(a + d * (factor + own + multiplier * offset)
                                          for a, d in zip(first, change))
                if snapping:
                    value = self.storage_type(_round_tween_value(v) for v in value)
                setter(self._compose(value, getter, constraint, alpha_only))
                return
            snapshot = constructor(tuple(start_value), tuple(change_value), options.snapping)
        factor = t._ease_time(elapsed, duration)
        value = getattr(snapshot, self._interpolate_name)(factor, own, multiplier, offset)
        if self.kind == 'color':
            value = list(value)
        elif self.kind == 'rect':
            value = Rect(*value)
        setter(self._compose(value, getter, constraint, alpha_only))


class _TypedBuiltinPlugin(_BuiltinPlugin):
    def __init__(self):
        super().__init__(*self._definition)


class FloatPlugin(_TypedBuiltinPlugin):
    _definition = ('scalar', np.float32, 0)


class DoublePlugin(_TypedBuiltinPlugin):
    _definition = ('scalar', np.float64, 0)


class IntPlugin(_TypedBuiltinPlugin):
    _definition = ('scalar', np.int32, 32)


class LongPlugin(_TypedBuiltinPlugin):
    _definition = ('scalar', np.int64, 64)


class UintPlugin(_TypedBuiltinPlugin):
    _definition = ('unsigned', np.uint32, 32)


class UlongPlugin(_TypedBuiltinPlugin):
    _definition = ('unsigned', np.uint64, 64)


class Vector2Plugin(_TypedBuiltinPlugin):
    _definition = ('vector', Vector2, 0)


class Vector3Plugin(_TypedBuiltinPlugin):
    _definition = ('vector', Vector3, 0)


class Vector4Plugin(_TypedBuiltinPlugin):
    _definition = ('vector', vec4f, 0)


class ColorPlugin(_TypedBuiltinPlugin):
    _definition = ('color', list, 0)


class RectPlugin(_TypedBuiltinPlugin):
    _definition = ('rect', Rect, 0)


class StringPlugin(_TypedBuiltinPlugin):
    _definition = ('string', str, 0)


class QuaternionPlugin(_TypedBuiltinPlugin):
    _definition = ('euler', Vector3, 0)


class Vector3ArrayPlugin(_TypedBuiltinPlugin):
    _definition = ('array', Vector3, 0)


_BUILTIN_PLUGIN_TYPES = frozenset((_BuiltinPlugin, FloatPlugin, DoublePlugin, IntPlugin, LongPlugin,
    UintPlugin, UlongPlugin, Vector2Plugin, Vector3Plugin, Vector4Plugin, ColorPlugin,
    RectPlugin, StringPlugin, QuaternionPlugin, Vector3ArrayPlugin))
_PLUGIN_CLASSES = {cls._definition: cls for cls in _BUILTIN_PLUGIN_TYPES if cls is not _BuiltinPlugin}
_PLUGIN_CLASSES.update({('scalar', float, 0): DoublePlugin,
                        ('scalar', int, 32): IntPlugin, ('scalar', int, 64): LongPlugin})
_PLUGINS = {}


def get_builtin_plugin(tween):
    explicit = tween.__dict__.get('_explicit_builtin_plugin')
    if explicit is not None:
        return explicit
    kind = tween._core_plugin_kind
    value_type = list if kind == 'color' else type(tween._end)
    if kind == 'euler':
        value_type = Vector3
    if kind == 'array':
        from .array import Vector3Array
        value_type = Vector3Array
    bits = 0
    if kind in ('scalar', 'unsigned'):
        bits = tween._scalar_bits
        plain_integer = not bits and (tween._integer if tween._initialized else value_type is int)
        if plain_integer:
            bits = tween._integer_bits or (32 if -(2**31) <= tween._end < 2**31 else 64)
            value_type = int
        else:
            value_type = tween._scalar_type
    key = kind, value_type, bits
    plugin = _PLUGINS.get(key)
    if plugin is None:
        cls = Vector3ArrayPlugin if kind == 'array' else _PLUGIN_CLASSES.get(key, _BuiltinPlugin)
        plugin = cls.__new__(cls)
        _BuiltinPlugin.__init__(plugin, *key)
        _PLUGINS[key] = plugin
    return plugin
