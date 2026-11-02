"""RGBA field edits reach prepared native work without frame-time polling."""
from array import array
from copy import copy, deepcopy
import gc
import math
import sys
import threading

import pytest

import infernux_tween as api
from infernux.lib._Infernux import _ColorTweenSnapshot, _EaseKernel


def make():
    manager, values = api.TweenManager(), [[2., 3., 4., 5.]]
    endpoint = [10., 13., 16., 19.]
    handle = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), endpoint, 1.)
    handle.set_auto_kill(False).set_ease(api.Ease.LINEAR)
    return manager, handle, values, endpoint


@pytest.mark.parametrize('custom_ease', [False, True])
def test_color_fields_copy_assignments_and_keep_component_edits_live(custom_ease):
    manager, handle, values, endpoint = make()
    endpoint[0] = 999
    handle.set_ease((lambda t, d, a, p: .5) if custom_ease else api.Ease.LINEAR)
    handle.force_init()
    assert handle.end_value == [10, 13, 16, 19]
    values[0][0] = 500
    assert handle.start_value[0] == 2
    start, change = [2, 3, 4, 5], [8, 10, 12, 14]
    handle.start_value, handle.change_value = start, change
    start[0] = change[0] = 999
    assert handle.start_value[0] == 2 and handle.change_value[0] == 8
    snapshot, job = handle._numeric_value, handle._numeric_job
    handle.start_value.r, handle.change_value.r = 5, 20
    handle.end_value[0] = 999
    handle.goto(.5)
    assert values[0] == [15, 8, 10, 12]
    assert type(values[0]) is list
    assert handle._numeric_value is snapshot and handle._numeric_job is job
    assert handle.end_value[0] == 999
    handle.plug_options.alpha_only = True
    values[0] = [100, 200, 300, 0]
    handle.start_value.a, handle.change_value.a = .25, .5
    handle.goto(.5)
    assert values[0] == [100, 200, 300, .5]
    assert handle._numeric_value is snapshot
    manager.clear()


def test_old_color_jobs_keep_their_storage_after_replacement_and_retirement():
    manager, handle, values, _ = make()
    handle.force_init()
    old_job, old_start, old_change = handle._numeric_job, handle.start_value, handle.change_value
    handle.start_value, handle.change_value = [20]*4, [40]*4
    old_start[0], old_change[0] = 4, 12
    del old_start, old_change
    gc.collect()
    assert old_job(.5) == [10, 8, 10, 12]
    handle.goto(.5)
    assert values[0] == [40]*4
    manager.clear()
    gc.collect()
    assert old_job(.5) == [10, 8, 10, 12]


def test_color_edits_through_retained_values_do_not_touch_a_recycled_handle():
    manager, values = api.TweenManager().init(True), [[2.,3.,4.,5.]]
    first = manager.to(lambda: values[0], lambda v: values.__setitem__(0,v), [10,13,16,19], 1.)
    first.set_ease(api.Ease.LINEAR).force_init()
    old_start, old_change, old_job = first.start_value, first.change_value, first._numeric_job
    first.kill()
    values[0] = [20.]*4
    second = manager.to(lambda: values[0], lambda v: values.__setitem__(0,v), [60.]*4, 1.)
    second.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    assert second is first
    old_start[0], old_change[0] = 4, 12
    assert old_job(.5) == [10,8,10,12]
    second.goto(.5)
    assert values[0] == [40.]*4
    manager.clear()


def test_color_list_slice_sort_reverse_and_value_copies_update_native_channels():
    manager, handle, values, _ = make()
    handle.force_init()
    handle.change_value = [0]*4
    color = handle.start_value
    color[::2] = [7, 9]
    handle.goto(.5)
    assert values[0] == [7, 3, 9, 5]
    color.reverse()
    handle.goto(.5)
    assert values[0] == [5, 9, 3, 7]
    color.sort()
    handle.goto(.5)
    assert values[0] == [3, 5, 7, 9]
    for clone in (copy(color), deepcopy(color), color.copy()):
        clone[0] = 500
        assert color[0] == 3
    before, job = list(color), handle._numeric_job
    with pytest.raises(TypeError):
        color[1:2] = [3, 4]
    with pytest.raises(TypeError):
        color.append(8)
    with pytest.raises(IndexError):
        color[4] = 8
    assert color == before and handle._numeric_job is job
    handle.goto(.5)
    assert values[0] == before
    manager.clear()


def test_color_from_publishes_a_value_copy_without_exposing_tween_storage():
    manager, handle, values, _ = make()
    handle.from_()
    assert type(values[0]) is list and values[0] == [10, 13, 16, 19]
    handle.start_value[0] = 99
    assert values[0][0] == 10
    manager.clear()


@pytest.mark.parametrize('start,change', [([.1,.2,.3,.4],[.3,.4,.5,.6]),
                                       ([4194304,3,-20,1],[1,-7,60,.25])])
def test_live_color_math_matches_immutable_single_precision_and_nested_offsets(start, change):
    manager, handle, _, _ = make()
    handle.force_init()
    handle.start_value, handle.change_value = start, change
    reference = _ColorTweenSnapshot(start, change).bind(_EaseKernel(1), 1)
    job = handle._numeric_job
    times = array('d', [0,.125,.375,.5,1])
    output = array('f', [0])*20
    job.sample_into(times, output, 1, 3, 2)
    for i, time in enumerate(times):
        expected = reference.sample_nested(time, 1, 3, 2)
        assert job.sample_nested(time, 1, 3, 2) == expected
        assert handle._numeric_value.interpolate(time, 1, 3, 2) == expected
        assert list(output[i*4:(i+1)*4]) == expected
    manager.clear()


def test_color_float_channels_keep_nonfinite_values_without_vector_validation():
    manager, handle, values, _ = make()
    handle.force_init()
    handle.start_value = [math.inf, -math.inf, math.nan, 1]
    handle.change_value = [0]*4
    handle.goto(.5)
    assert values[0][0] == math.inf and values[0][1] == -math.inf
    assert math.isnan(values[0][2]) and values[0][3] == 1
    handle.start_value[0] = math.nan
    handle.goto(.5)
    assert math.isnan(values[0][0])
    manager.clear()


def test_large_live_color_batch_freezes_inputs_and_releases_gil():
    manager, handle, _, _ = make()
    handle.force_init()
    handle.start_value, handle.change_value = [2]*4, [8]*4
    job = handle._numeric_job
    times, output = array('d', [.5])*1_000_000, array('f', [0])*4_000_000
    ready, armed, edited = threading.Event(), threading.Event(), threading.Event()
    def edit():
        ready.set()
        armed.wait()
        handle.start_value[0], handle.change_value[0] = 10, 20
        edited.set()
    thread, previous = threading.Thread(target=edit), sys.getswitchinterval()
    try:
        sys.setswitchinterval(10)
        thread.start()
        assert ready.wait(5)
        armed.set()
        job.sample_into(times, output)
        assert edited.is_set() and all(value == 6 for value in output)
        assert job(.5) == [20,6,6,6]
    finally:
        armed.set()
        sys.setswitchinterval(previous)
        thread.join(timeout=5)
        manager.clear()
