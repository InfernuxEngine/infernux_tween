"""Integer playback keeps integer storage across scalar and buffer APIs."""
from array import array

import numpy as np
import pytest

from infernux.lib._Infernux import _EaseKernel, _SignedIntegerTweenSnapshot
from infernux_tween import Ease, TweenManager


@pytest.mark.parametrize('bits,start', [(32, 10), (64, 6000000000)])
@pytest.mark.parametrize('output', ['array', 'numpy'])
def test_integer_jobs_write_portable_signed_buffers(bits, start, output):
    job = _SignedIntegerTweenSnapshot(start, start + 8, bits).bind(_EaseKernel(1), 1)
    times = array('d', [0, .25, .5, .75, 1])
    values = array('q', [0] * 5) if output == 'array' else np.empty(5, dtype=np.int64)
    job.sample_into(times, values)
    assert list(values) == [start, start + 2, start + 4, start + 6, start + 8]


def test_floating_endpoint_keeps_fractional_playback_with_an_integer_initial_value():
    manager, value = TweenManager(), [0]
    try:
        handle = manager.to(lambda: value[0], lambda result: value.__setitem__(0, result), 1., 1)
        handle.set_ease(Ease.LINEAR).goto(.25)
        assert value[0] == .25 and type(value[0]) is float
    finally:
        manager.clear()


def test_large_integer_values_keep_integer_setter_arguments_after_changing_values():
    manager, value = TweenManager(), [6000000000]
    try:
        handle = manager.to(lambda: value[0], lambda result: value.__setitem__(0, result), 6000000008, 1)
        handle.set_ease(Ease.LINEAR).set_auto_kill(False).goto(.25)
        assert value[0] == 6000000002 and type(value[0]) is int
        handle.change_values(6000001024, 6000001032).goto(.5)
        assert value[0] == 6000001028 and type(value[0]) is int
    finally:
        manager.clear()
