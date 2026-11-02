"""Declared scalar types survive playback, editing, loops and native buffers."""
from array import array

import numpy as np
import pytest

from infernux.lib._Infernux import _EaseKernel, _UInt64TweenSnapshot
import infernux_tween as api


DTYPES = (np.float32, np.float64, np.int32, np.int64, np.uint32, np.uint64)


@pytest.mark.parametrize('dtype', DTYPES)
def test_typed_setter_values_and_custom_ease_keep_the_declared_type(dtype):
    manager, values = api.TweenManager(), [dtype(2)]
    handle = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), dtype(10), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_loops(3, api.LoopType.INCREMENTAL)
    handle.goto(.25)
    assert type(values[0]) is dtype and values[0] == dtype(4)
    handle.change_values(4, 12)
    handle.goto(.5)
    assert type(values[0]) is dtype and values[0] == dtype(8)
    handle.set_ease(lambda time, duration, amplitude, period: .25)
    handle.goto(.5)
    assert type(values[0]) is dtype and values[0] == dtype(6)
    manager.clear()


@pytest.mark.parametrize('dtype,format_code', [(np.float32, 'f'), (np.float64, 'd'),
    (np.int32, 'i'), (np.int64, 'q'), (np.uint32, 'I'), (np.uint64, 'Q')])
@pytest.mark.parametrize('numpy_buffer', [False, True])
def test_typed_jobs_write_matching_numpy_and_standard_library_buffers(dtype, format_code, numpy_buffer):
    manager = api.TweenManager()
    handle = manager.to(lambda: dtype(2), lambda v: None, dtype(10), 1).set_ease(api.Ease.LINEAR)
    handle.force_init()
    options_type = api.FloatOptions if dtype is np.float32 else api.UintOptions if dtype is np.uint32 else api.NoOptions
    assert type(handle.plug_options) is options_type
    job = handle._numeric_job
    times = array('d', [0, .25, .5, .75, 1])
    values = np.empty(5, dtype=dtype) if numpy_buffer else array(format_code, [0] * 5)
    job.sample_into(times, values, 1, 3, 2)
    assert list(values) == [58, 60, 62, 64, 66]
    assert type(job(.5, 0)) is dtype
    manager.clear()


def test_replacing_empty_options_preserves_the_prepared_job():
    manager = api.TweenManager()
    handle = manager.to(lambda: np.float64(2), lambda v: None, np.float64(10), 1)
    handle.force_init()
    prepared = handle._numeric_job
    handle.plug_options = api.NoOptions()
    assert handle._numeric_job is prepared
    manager.clear()


def test_uint64_keeps_exact_integer_bits_above_the_double_mantissa():
    initial = 9007199254740993
    job = _UInt64TweenSnapshot(initial, 4).bind(_EaseKernel(1), 1)
    for time, expected in ((0., initial), (.25, initial + 1), (.5, initial + 2), (1., initial + 4)):
        assert type(job(time, 0)) is np.uint64 and int(job(time, 0)) == expected


@pytest.mark.parametrize('dtype', DTYPES)
def test_typed_builtin_plugin_can_be_reused_and_called_through_its_public_contract(dtype):
    manager, values = api.TweenManager(), [dtype(2)]
    handle = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), dtype(10), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    plugin = handle.get_plugin()
    assert plugin.value_type is dtype
    other = manager.to(plugin, lambda: dtype(2), values.append, dtype(10), 1).set_ease(api.Ease.LINEAR)
    other.goto(.25)
    assert type(values[-1]) is dtype and values[-1] == dtype(4)
    plugin.evaluate_and_apply(handle.plug_options, handle, False, handle.getter, handle.setter,
                              .25, handle.start_value, handle.change_value, 1., False, 0, api.UpdateNotice.NONE)
    assert type(values[0]) is dtype and values[0] == dtype(4)
    manager.clear()


def test_uint32_direction_options_remain_live_and_keep_independent_end_storage():
    manager, values = api.TweenManager(), [np.uint32(20)]
    handle = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), np.uint32(4), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).goto(.5)
    assert values[0] == np.uint32(12) and handle.plug_options.is_negative_change_value
    handle.plug_options.is_negative_change_value = False
    handle.goto(.5)
    assert values[0] == np.uint32(28) and handle.end_value == np.uint32(4)
    assert isinstance(handle.plug_options, api.UintOptions)
    manager.clear()


def test_numeric_conversion_overflow_propagates_without_retiring_the_target():
    manager, values = api.TweenManager().init(use_safe_mode=False), [np.uint64(2**64 - 1)]
    handle = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), np.uint64(0), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).pause()
    handle.goto(.5)
    with pytest.raises(OverflowError):
        handle.goto(1)
    assert handle.is_active() and int(values[0]) == 2**64 - 1 and manager._safe_mode_errors == 0
    manager.clear()
