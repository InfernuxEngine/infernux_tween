"""Mutable native arrays feed prepared sampling without frame-time rebuilding."""
from array import array
from copy import copy
import gc
import sys
import threading

import pytest
from infernux.lib import Vector3
from infernux.lib._Infernux import _EaseKernel, _TweenLiveSegments
import infernux_tween as api


def test_array_fields_keep_native_storage_and_changes_remain_independent():
    m, values = api.TweenManager(), [Vector3(2, 3, 4)]
    requested = api.Vector3Array([Vector3(10, 13, 16), Vector3(20, 23, 26)])
    h = m.to_array(lambda: values[0], lambda value: values.__setitem__(0, value), requested, [.5, .5])
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    assert h.end_value is not requested and type(h.plug_options) is api.Vector3ArrayOptions
    job = h._numeric_segments
    h.start_value[0].x = 5
    h.change_value[0] = Vector3(40, 50, 60)
    requested[0].x = 90
    h.end_value[0].x = 80
    h.goto(.25)
    assert tuple(values[0]) == (25, 28, 34) and h._numeric_segments is job
    assert h.end_value[0].x == 80 and requested[0].x == 90
    replacement = api.Vector3Array([Vector3(1, 2, 3), Vector3(4, 5, 6)])
    h.start_value = replacement
    assert h.start_value is replacement
    replacement[0].x = 10
    h.goto(.25)
    assert tuple(values[0]) == (30, 27, 33)
    m.clear()


def test_array_item_owns_its_fixed_storage_after_the_array_wrapper_is_deleted():
    values = api.Vector3Array([Vector3(1, 2, 3)])
    item = values[-1]
    del values
    gc.collect()
    item.x = 10
    assert tuple(item) == (10, 2, 3)


def test_copied_duration_options_update_the_clock_when_speed_is_changed():
    m, values = api.TweenManager(), [Vector3(0, 0, 0)]
    h = m.to_array(lambda: values[0], lambda value: values.__setitem__(0, value), [Vector3(2, 0, 0)], [.5])
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    options, prepared = copy(h.plug_options), h._numeric_segments
    assert h.get_plugin().get_speed_based_duration(options, 100, h.change_value) == 4
    assert h._numeric_segments is not prepared
    h.goto(.25)
    assert tuple(values[0]) == (.125, 0, 0)
    m.clear()


def test_builtin_array_factory_uses_native_execution_after_options_are_configured():
    m = api.TweenManager()
    h = m.to_array(lambda: Vector3(), lambda v: None, [Vector3(1, 2, 3)], [1])
    plugin = h.get_plugin()
    values = []
    other = m.to(plugin, lambda: Vector3(), values.append, api.Vector3Array([Vector3(2, 4, 6)]), 1)
    other.plug_options._durations = [1]
    other.set_ease(api.Ease.LINEAR).goto(.5)
    assert tuple(values[-1]) == (1, 2, 3)
    m.clear()


def test_declared_array_axis_flags_remain_visible_with_unconstrained_execution():
    m, values = api.TweenManager(), [Vector3()]
    h = m.to_array(lambda: values[0], lambda value: values.__setitem__(0, value), [Vector3(2, 4, 6)], [1])
    flags = api.AxisConstraint.X | api.AxisConstraint.Y
    h.set_options(flags).set_ease(api.Ease.LINEAR).force_init()
    assert h.plug_options.axis_constraint == flags
    h.goto(.5)
    assert tuple(values[0]) == (1, 2, 3)
    m.clear()


def test_retimed_array_uses_original_segment_durations_for_custom_ease():
    m, values, calls = api.TweenManager(), [Vector3()], []
    h = m.to_array(lambda: values[0], lambda value: values.__setitem__(0, value), [Vector3(2, 0, 0), Vector3(6, 0, 0)], [.5, .5])
    h.set_ease(lambda time, duration, amplitude, period: calls.append((time, duration)) or time / duration)
    h.set_auto_kill(False).force_init()
    h.change_end_value([Vector3(2, 0, 0), Vector3(6, 0, 0)], 2)
    h.goto(.75)
    assert calls[-1] == (.25, .5) and tuple(values[0]) == (4, 0, 0)
    h.goto(1.25)
    assert calls[-1] == (1., .5) and tuple(values[0]) == (4, 0, 0)
    m.clear()


def test_bulk_live_sampling_freezes_values_before_releasing_the_gil():
    start, change = api.Vector3Array([Vector3()]), api.Vector3Array([Vector3(2, 4, 6)])
    job = _TweenLiveSegments(start, change, [1])
    progress = array('d', [.5]) * 250_000
    output = array('f', [0]) * (len(progress) * 3)
    armed, changed = threading.Event(), threading.Event()
    def edit():
        armed.wait()
        start[0].x = 1000
        change[0].x = 1000
        changed.set()
    thread = threading.Thread(target=edit)
    previous = sys.getswitchinterval()
    try:
        sys.setswitchinterval(10)
        thread.start()
        armed.set()
        job.sample_into(progress, output, 1, _EaseKernel(1))
        assert changed.is_set()
        assert all(output[i:i+3] == array('f', [1, 2, 3]) for i in range(0, len(output), 3))
        assert tuple(job.sample(.5, 1, _EaseKernel(1), 0)) == (1500, 2, 3)
    finally:
        armed.set()
        sys.setswitchinterval(previous)
        thread.join(timeout=5)
