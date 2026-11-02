"""Prepared vector jobs observe field edits without Python frame-time polling."""
from array import array
import gc
import sys
import threading

import pytest
from infernux.lib import Vector2, Vector3, vec4f
from infernux.lib import _Infernux as native
import infernux_tween as api


VECTORS = ((Vector2, 2), (Vector3, 3), (vec4f, 4))


@pytest.mark.parametrize('kind,channels', VECTORS)
@pytest.mark.parametrize('custom_ease', [False, True])
def test_vector_fields_read_in_place_edits_and_copy_supplied_values(kind, channels, custom_ease):
    manager = api.TweenManager()
    initial, endpoint = kind(*([2] * channels)), kind(*([10] * channels))
    values = [initial]
    handle = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), endpoint, 1)
    endpoint.x = 100
    handle.set_ease((lambda t, d, a, p: .5) if custom_ease else api.Ease.LINEAR)
    handle.set_auto_kill(False).force_init()
    initial.x = 200
    assert handle.start_value.x == 2 and handle.end_value.x == 10
    first, change = kind(*([4] * channels)), kind(*([12] * channels))
    handle.start_value, handle.change_value = first, change
    first.x = change.x = 300
    assert handle.start_value.x == 4 and handle.change_value.x == 12
    job, snapshot = handle._numeric_job, handle._numeric_value
    handle.start_value.x, handle.change_value.x = 6, 8
    handle.end_value.x = 999
    handle.goto(.5)
    assert tuple(values[0]) == (10,) * channels
    assert handle._numeric_job is job and handle._numeric_value is snapshot
    assert handle.end_value.x == 999
    manager.clear()


@pytest.mark.parametrize('kind,channels', VECTORS)
def test_live_vector_jobs_pin_storage_and_preserve_old_jobs_after_rebinding(kind, channels):
    manager, values = api.TweenManager(), [kind(*([2] * channels))]
    handle = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), kind(*([10] * channels)), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    old_job, old_start, old_change = handle._numeric_job, handle.start_value, handle.change_value
    handle.start_value, handle.change_value = kind(*([20] * channels)), kind(*([40] * channels))
    old_start.x, old_change.x = 4, 12
    del old_start, old_change
    gc.collect()
    assert tuple(old_job(.5)) == (10,) + (6,) * (channels - 1)
    handle.goto(.5)
    assert tuple(values[0]) == (40,) * channels
    manager.clear()
    gc.collect()
    assert tuple(old_job(.5)) == (10,) + (6,) * (channels - 1)


@pytest.mark.parametrize('kind,channels', VECTORS)
@pytest.mark.parametrize('snapping', [False, True])
def test_live_vector_native_math_matches_immutable_recipe(kind, channels, snapping):
    start, change = kind(*([1.25] * channels)), kind(*([7.5] * channels))
    snapshot = getattr(native, f'_LiveVector{channels}TweenSnapshot')(start, change, snapping)
    immutable = getattr(native, f'_Vector{channels}TweenSnapshot')(tuple(start), tuple(change), snapping)
    job = snapshot.bind(native._EaseKernel(1), 1)
    times, output = array('d', [0, .125, .375, .5, 1]), array('f', [0]) * (5 * channels)
    job.sample_into(times, output, 1, 3, 2)
    for i, time in enumerate(times):
        expected = tuple(immutable.interpolate(time, 1, 3, 2))
        assert tuple(output[i * channels:(i + 1) * channels]) == expected
        assert tuple(job.sample_nested(time, 1, 3, 2)) == expected
        assert tuple(snapshot.interpolate(time, 1, 3, 2)) == expected
    change.x = 20
    start.x = 10
    assert tuple(job(.5)) == (20,) + tuple(immutable.interpolate(.5))[1:]


@pytest.mark.parametrize('kind,channels', VECTORS)
def test_large_live_vector_batches_freeze_inputs_before_releasing_the_gil(kind, channels):
    start, change = kind(*([2] * channels)), kind(*([8] * channels))
    job = getattr(native, f'_LiveVector{channels}TweenSnapshot')(start, change).bind(native._EaseKernel(1), 1)
    times, output = array('d', [.5]) * 250_000, array('f', [0]) * (250_000 * channels)
    ready, armed, edited = threading.Event(), threading.Event(), threading.Event()
    def edit():
        ready.set()
        armed.wait()
        start.x, change.x = 10, 20
        edited.set()
    thread = threading.Thread(target=edit)
    previous = sys.getswitchinterval()
    try:
        sys.setswitchinterval(10)
        thread.start()
        assert ready.wait(5), "editing thread did not reach the sampling handoff"
        armed.set()
        job.sample_into(times, output)
        assert edited.is_set() and all(value == 6 for value in output)
        assert tuple(job(.5)) == (20,) + (6,) * (channels - 1)
    finally:
        armed.set()
        sys.setswitchinterval(previous)
        thread.join(timeout=5)
