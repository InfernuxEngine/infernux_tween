"""Declared scalar storage and native recipes, separate from timeline control."""
import numpy as np

from infernux.lib._Infernux import (
    _ScalarTweenSnapshot, _Float32TweenSnapshot, _SignedIntegerTweenSnapshot,
    _UInt32TweenSnapshot, _UInt64TweenSnapshot, _round_tween_value,
)
from .core import _FloatTweener, TweenerCore


class _NumpyScalarTweener(_FloatTweener):
    @TweenerCore.start_value.setter
    def start_value(self, value):
        TweenerCore.start_value.fset(self, self._scalar_type(value))

    @TweenerCore.end_value.setter
    def end_value(self, value):
        self._end = self._scalar_type(value)

    @TweenerCore.change_value.setter
    def change_value(self, value):
        TweenerCore.change_value.fset(self, self._scalar_type(value))

    def _convert_start_value(self, value):
        return self._scalar_type(value)

    def _relative_value(self, current, value):
        return self._scalar_type(current) + self._scalar_type(value)

    def _set_values(self, start, end):
        self._start, self._end = self._scalar_type(start), self._scalar_type(end)
        self._delta = self._end - self._start
        self._compile_numeric_value()

    def _compile_numeric_value(self):
        self._numeric_value = self._snapshot_type(self._start, self._delta, self._snapping)
        self._numeric_rounding = True
        self._bind_numeric_sampler()

    def _snap(self, value, *, all_channels=False):
        return self._scalar_type(_round_tween_value(value))


class _Float32Tweener(_NumpyScalarTweener):
    _scalar_type = np.float32
    _snapshot_type = _Float32TweenSnapshot


class _Float64Tweener(_NumpyScalarTweener):
    _scalar_type = np.float64
    _snapshot_type = _ScalarTweenSnapshot
    _native_bind_name = 'bind_float64'
    _native_interpolate_name = 'interpolate_float64'


class _SignedScalarTweener(_NumpyScalarTweener):
    def _relative_value(self, current, value):
        sign = 1 << (self._scalar_bits - 1)
        return self._scalar_type(((int(current) + int(value) + sign) & ((sign << 1) - 1)) - sign)

    def _set_values(self, start, end):
        self._integer, self._integer_bits = True, self._scalar_bits
        self._numeric_value = _SignedIntegerTweenSnapshot(int(start), int(end), self._scalar_bits)
        self._start, self._end, self._delta = (self._scalar_type(value) for value in
            (self._numeric_value.start_value, self._numeric_value.end_value, self._numeric_value.change_value))
        self._bind_numeric_sampler()

    def _refresh_core_value(self):
        self._numeric_value = _SignedIntegerTweenSnapshot(
            int(self._start), int(self._start) + int(self._delta), self._scalar_bits)
        self._bind_numeric_sampler()

    def _distance(self):
        return abs(int(self._delta))


class _Int32Tweener(_SignedScalarTweener):
    _scalar_type, _scalar_bits = np.int32, 32
    _native_bind_name, _native_interpolate_name = 'bind_int32', 'interpolate_int32'


class _Int64Tweener(_SignedScalarTweener):
    _scalar_type, _scalar_bits = np.int64, 64
    _native_bind_name, _native_interpolate_name = 'bind_int64', 'interpolate_int64'


class _UnsignedScalarTweener(_NumpyScalarTweener):
    _core_plugin_kind = 'unsigned'
    _negative_change = False

    def _relative_value(self, current, value):
        return self._scalar_type((int(current) + int(value)) & ((1 << self._scalar_bits) - 1))

    def _set_values(self, start, end):
        self._integer = True
        self._start, self._end = self._scalar_type(start), self._scalar_type(end)
        first, last = int(self._start), int(self._end)
        self._negative_change = last < first
        self._delta = self._scalar_type(abs(last - first) if self._scalar_bits == 32 else (last - first) & ((1 << 64) - 1))
        self._compile_numeric_value()

    def _refresh_core_value(self):
        self._compile_numeric_value()

    def _core_option_changed(self, storage):
        if self._numeric_value is not None:
            self._compile_numeric_value()


class _UInt32Tweener(_UnsignedScalarTweener):
    _scalar_type, _scalar_bits = np.uint32, 32

    def _compile_numeric_value(self):
        self._numeric_value = _UInt32TweenSnapshot(int(self._start), int(self._delta), self._negative_change)
        self._bind_numeric_sampler()


class _UInt64Tweener(_UnsignedScalarTweener):
    _scalar_type, _scalar_bits = np.uint64, 64

    def _compile_numeric_value(self):
        self._numeric_value = _UInt64TweenSnapshot(int(self._start), int(self._delta))
        self._bind_numeric_sampler()


_NUMPY_TWEENERS = {kind._scalar_type: kind for kind in (
    _Float32Tweener, _Float64Tweener, _Int32Tweener, _Int64Tweener, _UInt32Tweener, _UInt64Tweener)}
