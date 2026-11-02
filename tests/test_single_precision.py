"""Typed scalar playback and buffer jobs keep their declared precision."""
from array import array
import sys
import threading

import numpy as np
import pytest

from infernux.lib._Infernux import _EaseKernel, _Float32TweenSnapshot
from infernux_tween import Ease, FloatOptions, TweenManager


def test_single_precision_playback_keeps_dtype_and_live_options():
    manager, values = TweenManager(), [np.float32(2)]
    tween = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), np.float32(11), 1)
    tween.set_ease(Ease.LINEAR).set_auto_kill(False).goto(.25)
    assert type(values[0]) is np.float32 and values[0] == np.float32(4.25)
    assert isinstance(tween.plug_options, FloatOptions)
    tween.plug_options.snapping = True
    tween.goto(.25)
    assert type(values[0]) is np.float32 and values[0] == np.float32(4)
    tween.set_options(False).change_values(2., 12.)
    tween.goto(.25)
    assert type(values[0]) is np.float32 and values[0] == np.float32(4.5)
    manager.clear()


def test_single_precision_snapping_rounds_the_expression_before_its_float_store():
    manager, values = TweenManager(), [np.float32(4194304)]
    tween = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), np.float32(4194305), 1)
    tween.set_ease(Ease.LINEAR).set_options(True).goto(.51)
    assert type(values[0]) is np.float32 and values[0] == np.float32(4194305)
    manager.clear()


@pytest.mark.parametrize('output', ['array', 'numpy'])
def test_single_precision_buffer_jobs_write_float32_without_python_scalar_conversion(output):
    job = _Float32TweenSnapshot(2, 8).bind(_EaseKernel(1), 1)
    times = array('d', [0, .25, .5, .75, 1])
    result = array('f', [0] * 5) if output == 'array' else np.empty(5, dtype=np.float32)
    job.sample_into(times, result)
    assert list(result) == [2, 4, 6, 8, 10]
    job.sample_into(times, result, 1, 3, 2)
    assert list(result) == [58, 60, 62, 64, 66]
    assert type(job(.5, 0)) is np.float32


def test_single_precision_value_edits_and_explicit_plugin_keep_the_prepared_route():
    manager, values = TweenManager(), [np.float32(2)]
    tween = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), np.float32(10), 1)
    tween.set_ease(Ease.LINEAR).set_auto_kill(False).force_init()
    tween.start_value, tween.change_value, tween.end_value = 5., 40., 20.
    assert all(type(value) is np.float32 for value in (tween.start_value, tween.change_value, tween.end_value))
    tween.goto(.25)
    assert values[0] == np.float32(15)
    job = tween._numeric_job
    tween.goto(.5)
    assert tween._numeric_job is job
    other = manager.to(tween.get_plugin(), lambda: np.float32(0), values.append, 8., 1).set_ease(Ease.LINEAR)
    other.goto(.25)
    assert other._numeric_job is not None and type(values[-1]) is np.float32 and values[-1] == np.float32(2)
    manager.clear()


def test_large_single_precision_buffer_job_releases_the_gil():
    job = _Float32TweenSnapshot(2, 8).bind(_EaseKernel(1), 1)
    times = np.full(100000, .5, dtype=np.float64)
    result = np.empty(100000, dtype=np.float32)
    armed, observed = threading.Event(), threading.Event()
    def work():
        armed.wait()
        observed.set()
    worker = threading.Thread(target=work)
    previous = sys.getswitchinterval()
    try:
        sys.setswitchinterval(10)
        worker.start()
        armed.set()
        job.sample_into(times, result)
        assert observed.is_set() and np.all(result == np.float32(6))
    finally:
        sys.setswitchinterval(previous)
        armed.set()
        worker.join(timeout=5)
