"""Rotation storage, option copies and native jobs preserve their live inputs."""
from array import array
from copy import copy
import sys
import threading

import pytest
from infernux.lib import Vector3, quatf
import infernux_tween as api
from infernux_tween.rotation import EulerTweener


@pytest.mark.parametrize('explicit', [False, True])
def test_rotation_fields_keep_their_type_and_prepared_job_reads_in_place_edits(explicit):
    m, values = api.TweenManager(), [quatf.euler(10, 20, 30)]
    requested = Vector3(100, 120, 140)
    get, put = lambda: values[0], lambda value: values.__setitem__(0, value)
    h = m.add(EulerTweener(get, put, requested, 1)) if explicit else m.to(get, put, requested, 1)
    requested.x = 300
    assert tuple(h.end_value) == (100, 120, 140)
    assert type(h.plug_options) is api.QuaternionOptions
    assert tuple(h.plug_options.up) == (0, 0, 0)
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    h.start_value, h.change_value = Vector3(0, 0, 0), Vector3(0, 90, 0)
    prepared = h._numeric_job
    h.start_value.y = 30
    h.goto(.5)
    assert tuple(values[0]) == tuple(quatf.euler(0, 75, 0)) and h._numeric_job is prepared
    h.end_value.x = 360
    h.goto(.5)
    assert tuple(values[0]) == tuple(quatf.euler(0, 75, 0))
    assert h.get_plugin().value_type is quatf and h.get_plugin().storage_type is Vector3
    m.clear()


def test_annotated_quaternion_getter_resolves_options_without_capturing_values():
    m, calls = api.TweenManager(), [0]
    def get() -> quatf:
        calls[0] += 1
        return quatf.identity()
    h = m.to(get, lambda value: None, Vector3(0, 90, 0), 1)
    assert type(h.plug_options) is api.QuaternionOptions and calls[0] == 0
    assert not h.is_initialized()
    h.force_init()
    assert calls[0] == 1
    m.clear()


def test_quaternion_option_vectors_are_copied_and_old_options_detach():
    m = api.TweenManager()
    h = m.add(EulerTweener(lambda: quatf.identity(), lambda value: None, Vector3(0, 90, 0), 1))
    h.force_init()
    requested = Vector3(1, 2, 3)
    h.plug_options.up = requested
    requested.x = 99
    assert tuple(h.plug_options.up) == (1, 2, 3)
    old, separate = h.plug_options, copy(h.plug_options)
    separate.up.x = 4
    assert tuple(h.plug_options.up) == (1, 2, 3)
    h.plug_options = separate
    separate.up.x = 88
    old.up.x = 77
    assert tuple(h.plug_options.up) == (4, 2, 3)
    m.clear()


def test_explicit_builtin_rotation_plugin_uses_the_prepared_native_route():
    m, values = api.TweenManager(), [quatf.identity()]
    original = m.add(EulerTweener(lambda: quatf.identity(), lambda value: None, Vector3(0, 90, 0), 1))
    plugin = original.get_plugin()
    h = m.to(plugin, lambda: values[0], lambda value: values.__setitem__(0, value), Vector3(0, 90, 0), 1)
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).goto(.5)
    assert isinstance(h, api.TweenerCore) and tuple(values[0]) == tuple(quatf.euler(0, 45, 0))
    assert h._numeric_job is not None
    m.clear()


@pytest.mark.parametrize('mode', [api.RotateMode.FAST, api.RotateMode.WORLD_AXIS_ADD, api.RotateMode.LOCAL_AXIS_ADD])
def test_bulk_rotation_sampling_freezes_vectors_before_releasing_the_gil(mode):
    m = api.TweenManager()
    h = m.add(EulerTweener(lambda: quatf.identity(), lambda value: None, Vector3(0, 90, 0), 1, mode))
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    job = h._numeric_job
    expected = array('f', tuple(job(.5)))
    times, values = array('d', [.5]) * 100_000, array('f', [0]) * 400_000
    armed, edited = threading.Event(), threading.Event()
    def edit():
        armed.wait()
        h.start_value.y = 90
        edited.set()
    thread = threading.Thread(target=edit)
    previous = sys.getswitchinterval()
    try:
        sys.setswitchinterval(10)
        thread.start()
        armed.set()
        job.sample_into(times, values)
        assert edited.is_set()
        assert all(values[i:i+4] == expected for i in range(0, len(values), 4))
        assert tuple(job(.5)) == pytest.approx(tuple(quatf.euler(0, 135, 0)), abs=4e-7, rel=0)
    finally:
        armed.set()
        sys.setswitchinterval(previous)
        thread.join(timeout=5)
        m.clear()
