"""UTF-16 string tweens with immutable native text plans and shared scrambling."""
from enum import Enum
from collections.abc import MutableSequence
from weakref import WeakSet

from infernux.lib._Infernux import _EaseKernel, _StringTweenSnapshot, _StringScrambleAlphabet

from .core import TweenerCore, _UNSET
from ._builtin_plugins import _Options, _option_field


_LINEAR = _EaseKernel(1)


class ScrambleMode(Enum):
    NONE = 0
    ALL = 1
    UPPERCASE = 2
    LOWERCASE = 3
    NUMERALS = 4
    CUSTOM = 5


class _Characters(MutableSequence):
    """Fixed-size UTF-16 characters shared by copied options.

    Edits publish a new immutable alphabet to attached plans. Sampling never
    polls the Python array and already prepared native work stays immutable.
    """
    def __init__(self, values, *, shuffled=False):
        self._alphabet = _StringScrambleAlphabet(''.join(values), shuffled)
        self._data = self._alphabet.characters
        self._owners = WeakSet()

    def __len__(self):
        return len(self._data)

    def __getitem__(self, index):
        return self._data[index]

    def __iter__(self):
        return iter(self._data)

    def __setitem__(self, index, value):
        replacement = list(value) if isinstance(index, slice) else [value]
        if any(not isinstance(v, str) or len(v.encode('utf-16-le', 'surrogatepass')) != 2 for v in replacement):
            raise ValueError('characters must each contain one UTF-16 code unit')
        if isinstance(index, slice) and len(replacement) != len(self._data[index]):
            raise TypeError('character arrays have a fixed size')
        self._data[index] = replacement if isinstance(index, slice) else value
        self._alphabet = _StringScrambleAlphabet(''.join(self._data), False)
        for owner in self._owners:
            if owner._scramble_chars is self:
                owner._bind_numeric_sampler()

    def __delitem__(self, index):
        raise TypeError('character arrays have a fixed size')

    def insert(self, index, value):
        raise TypeError('character arrays have a fixed size')


class StringOptions(_Options):
    _fields = (('rich_text_enabled', '_rich_text'), ('scramble_mode', '_scramble_mode'),
               ('scrambled_chars', '_scramble_chars'),
               ('_start_value_stripped_length', '_start_value_stripped_length'),
               ('_change_value_stripped_length', '_change_value_stripped_length'))
    _defaults = (('rich_text_enabled', False), ('scramble_mode', ScrambleMode.NONE),
                 ('scrambled_chars', None), ('_start_value_stripped_length', 0),
                 ('_change_value_stripped_length', 0))
    rich_text_enabled = _option_field('rich_text_enabled', '_rich_text')
    scramble_mode = _option_field('scramble_mode', '_scramble_mode')
    _chars = _option_field('scrambled_chars', '_scramble_chars')
    _start_value_stripped_length = _option_field('_start_value_stripped_length', '_start_value_stripped_length')
    _change_value_stripped_length = _option_field('_change_value_stripped_length', '_change_value_stripped_length')

    @property
    def scrambled_chars(self):
        return self._chars

    @scrambled_chars.setter
    def scrambled_chars(self, value):
        self._chars = value if value is None or isinstance(value, _Characters) else _Characters(value)


class StringTweener(TweenerCore):
    _core_plugin_kind = 'string'

    def __init__(self, getter, setter, end_value, duration):
        self._string_snapshot = self._string_plan = self._sample_string = None
        self._rich_text = False
        self._scramble_mode = ScrambleMode.NONE
        self._scramble_chars = None
        self._start_value_stripped_length = self._change_value_stripped_length = 0
        super().__init__(getter, setter, end_value, duration)

    def _storage_default(self):
        return None

    def set_options(self, rich_text_enabled: bool, scramble_mode: ScrambleMode = ScrambleMode.NONE,
                    scramble_chars: str | None = None):
        if not self._active:
            return self
        if type(rich_text_enabled) is not bool or not isinstance(scramble_mode, ScrambleMode):
            raise TypeError("string options require bool and ScrambleMode")
        if scramble_chars is not None and not isinstance(scramble_chars, str):
            raise TypeError("scramble_chars must be str or None")
        self._rich_text, self._scramble_mode = rich_text_enabled, scramble_mode
        if scramble_chars:
            self._scramble_chars = _Characters(scramble_chars, shuffled=True)
        self._bind_numeric_sampler()
        return self

    def _set_relative(self, relative):
        super()._set_relative(relative)
        self._bind_numeric_sampler()

    def _initialize(self):
        if self._start is not None:
            return
        start, end = self._getter(), self._end
        if start is not None and not isinstance(start, str):
            raise TypeError("String tween getter must return str or None")
        start = "" if start is None else start
        if self._manual_start is not _UNSET:
            start = self._manual_start
        if self._from:
            if self._from_value is _UNSET:
                start, end = end, start
            else:
                first = "" if self._from_value is None else self._from_value
                start = first + start if self._from_relative else first
        if self._from and self._reset_relative_on_from_startup:
            self._relative = False
        self._set_values(start, end)

    def _set_values(self, start, end):
        self._start, self._end = start, end
        self._delta = end
        self._string_snapshot = _StringTweenSnapshot(start, end)
        self._start_value_stripped_length = self._string_snapshot.start_length(True)
        self._change_value_stripped_length = self._string_snapshot.length(True)
        self._bind_numeric_sampler()

    def _refresh_core_value(self):
        self._string_snapshot = _StringTweenSnapshot(self._start, self._delta)
        self._bind_numeric_sampler()

    def _core_option_changed(self, storage):
        self._core_options_changed()

    def _core_options_changed(self):
        self._bind_numeric_sampler()

    def _bind_numeric_sampler(self):
        if self._string_snapshot is not None:
            if self._scramble_chars is not None:
                self._scramble_chars._owners.add(self)
            self._string_plan = self._string_snapshot.bind(self._numeric_ease or _LINEAR, self._duration,
                self._rich_text, self._relative, self._scramble_mode.value,
                self._scramble_chars._alphabet if self._scramble_chars is not None else None,
                self._start_value_stripped_length, self._change_value_stripped_length)
            self._sample_string = self._string_plan.__call__ if self._numeric_ease is not None else None

    def _distance(self):
        return self._string_snapshot.length(self._rich_text)

    def _apply(self, progress, cycle, previous, callbacks):
        own = self._incremental_cycles(cycle, False)
        value = (self._sample_string(progress, own) if self._sample_string is not None else
                 self._string_plan.interpolate(self._ease(progress), own))
        self._setter(value)

    def _on_despawn(self):
        super()._on_despawn()
        self._start = self._end = self._delta = ""
        self._string_snapshot = self._string_plan = self._sample_string = self._scramble_chars = None
