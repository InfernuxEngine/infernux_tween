"""Native segment arrays, separate from shared timeline scheduling."""
from math import inf
from collections.abc import MutableSequence
from weakref import WeakSet

from infernux.lib._Infernux import (
    _TweenVector3Array as Vector3Array, _TweenLiveSegments, _tween_array_duration,
    _round_tween_value,
)
from .core import Tween, _VectorTweener, _UNSET, _f32
from .ease import Ease, resolve_ease


def _array(values):
    return values if isinstance(values, Vector3Array) else Vector3Array(values)


class _Durations(MutableSequence):
    """Shared option data publishes clock updates when edited, never on frames."""
    def __init__(self, values):
        self._values = [_f32(v) for v in values]
        self._owners = WeakSet()

    def __len__(self): return len(self._values)
    def __getitem__(self, index): return self._values[index]

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            value = [_f32(v) for v in value]
            if len(value) != len(self._values[index]):
                raise TypeError('duration arrays have a fixed size')
        else:
            value = _f32(value)
        self._values[index] = value
        for owner in self._owners:
            if owner._durations is self and owner._segment_starts is not None:
                owner._compile_segments()

    def __delitem__(self, index): raise TypeError('duration arrays have a fixed size')
    def insert(self, index, value): raise TypeError('duration arrays have a fixed size')


class _ArrayTweener(_VectorTweener):
    _core_plugin_kind = 'array'

    def __init__(self, getter, setter, end_values, durations, total_duration=None):
        if not end_values or durations is not None and len(end_values) != len(durations):
            raise ValueError("end_values and durations must have the same nonzero length")
        super().__init__(getter, setter, end_values[-1], _tween_array_duration(durations) if total_duration is None else total_duration)
        self._end_values = Vector3Array(end_values) if total_duration is None else _array(end_values)
        self._durations = _Durations(durations) if durations is not None else None
        self._segment_starts = self._segment_changes = None
        self._segment_duration = self._duration
        self._no_from = True
        self._manual_segments = None
        self._startup_mode = None
        self._startup_offsets = None
        self._startup_rotation_getter = None
        self._array_constraint = 0

    def _storage_default(self):
        return None

    @property
    def start_value(self):
        return self._segment_starts if self._initialized else self.__dict__.get('_pending_start_value')

    @start_value.setter
    def start_value(self, value):
        if self._initialized:
            self._segment_starts = _array(value)
            self._start = self._segment_starts[0]
            self._compile_segments()
        else:
            self._pending_start_value = value

    @property
    def end_value(self):
        return self._end_values

    @end_value.setter
    def end_value(self, value):
        self._end_values = _array(value)
        self._end = self._end_values[-1]

    @property
    def change_value(self):
        return self._segment_changes if self._initialized else self.__dict__.get('_pending_change_value')

    @change_value.setter
    def change_value(self, value):
        if self._initialized:
            self._segment_changes = _array(value)
            self._compile_segments()
        else:
            self._pending_change_value = value

    def _refresh_core_value(self):
        if self._start is not None:
            self._normalize_constraint(self._start)
        self._compile_segments()

    def _normalize_constraint(self, value):
        # Preserve declared options while specializing the executable axis.
        self._array_constraint = int(self._constraint) if self._constraint in (2, 4, 8) else 0

    def _core_option_changed(self, storage):
        if storage == '_durations' and self._segment_starts is not None:
            if not isinstance(self._durations, _Durations):
                self._durations = _Durations(self._durations)
            self._compile_segments()
        else:
            super()._core_option_changed(storage)

    def _initialize(self):
        if self._startup_mode is not None:
            self._relative = self._speed_based = False
            if self._start is None:
                self._ease_source = Ease.OUT_QUAD if self._startup_mode == "punch" else Ease.LINEAR
                self._assign_ease(resolve_ease(self._ease_source, *self._ease_args,
                                               duration=lambda: self._ease_duration))
                if self._startup_rotation_getter is not None:
                    from .rotation import _rotate_offset
                    rotation = self._startup_rotation_getter()
                    self._startup_offsets = tuple(_rotate_offset(rotation, point) for point in self._startup_offsets)
                    self._startup_rotation_getter = None
        super()._initialize()

    def _on_despawn(self):
        super()._on_despawn()
        self._startup_rotation_getter = self._startup_offsets = None
        self._manual_segments = None
        self._end_values = self._segment_starts = self._segment_changes = None
        self._durations = ()
        self._numeric_segments = self._sample_segments = None

    @property
    def _ease_duration(self):
        return self._segment_duration

    def _ensure_initialized(self):
        if not self._initialized:
            self._initialize()
            if self._speed_based:
                self._duration = _f32(self.get_plugin().get_speed_based_duration(self.plug_options, self._duration, self._segment_changes))
        return Tween._ensure_initialized(self)

    def _set_values(self, start, end):
        if self._startup_offsets is not None:
            self._end_values = _array(start + offset for offset in self._startup_offsets)
            end = self._end_values[-1]
        starts, ends = [], []
        for index, value in enumerate(self._end_values):
            first = (self._manual_segments[index] if self._manual_segments is not None
                     else start if index == 0 else ends[-1])
            if self._relative and not self._initialized:
                first = start if index == 0 else ends[-1]
                value = self._relative_value(first, value)
            starts.append(first)
            ends.append(value)
        self._segment_starts = _array(starts)
        # Startup owns a copy of requested ends; public field writes retain
        # references to the explicitly assigned native arrays.
        for index, value in enumerate(ends):
            self._end_values[index] = value
        self._segment_changes = _array(b - a for a, b in zip(starts, ends))
        self._start, self._end = starts[0], ends[-1]
        self._delta = self._end - self._start
        self._compile_segments()

    def _compile_segments(self):
        if not isinstance(self._durations, _Durations):
            self._durations = _Durations(self._durations)
        self._durations._owners.add(self)
        self._numeric_segments = _TweenLiveSegments(self._segment_starts, self._segment_changes, self._durations)
        self._sample_segments = self._numeric_segments.sample_time

    def _change_values(self, *, start=_UNSET, end=_UNSET, duration=-1, snap_start=False):
        if not self._active or self._parent is not None:
            return self
        if start is not _UNSET:
            if len(start) != len(self._durations):
                raise ValueError("array starts must match the segment count")
            self._manual_segments, start = tuple(start), start[0]
        if end is not _UNSET:
            if len(end) != len(self._durations):
                raise ValueError("array ends must match the segment count")
            self._end_values = _array(end)
            end = end[-1]
        if snap_start:
            self._manual_segments = None
        return super()._change_values(start=start, end=end, duration=duration, snap_start=snap_start)

    def _distance(self):
        return sum(change.magnitude for change in self._segment_changes)

    def _apply(self, progress, cycle, previous, callbacks):
        setter, constraint, snapping = self._setter, self._array_constraint, self._snapping
        if constraint:
            getter = self._getter
        segments = self._numeric_segments
        duration = self._duration
        incremental = self._incremental_cycles(cycle)
        if duration == 0:
            value = segments.interpolate(0, 1., incremental)
        else:
            elapsed = self._position - self._delay if duration == inf else progress * duration
            if self._numeric_ease is not None:
                value = self._sample_segments(elapsed, duration, self._numeric_ease, incremental)
            else:
                segment = segments.locate_time(elapsed, duration)
                self._segment_duration = segment.width
                fraction = self._ease(segment.progress) if segment.width else 1.0
                value = segments.interpolate(segment.index, fraction, incremental)
        if constraint:
            current = getter()
            components = [v if constraint & (2 << i) else current[i] for i, v in enumerate(value)]
            value = type(value)(*components)
        if snapping:
            value = _round_tween_value(value, constraint)
        setter(value)
