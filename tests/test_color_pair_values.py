"""Paired colors own writable float32 fields and enter timelines by value."""
from copy import copy, deepcopy
import pickle
import gc

import numpy as np
import pytest

from infernux.lib import SceneManager
from infernux.components.builtin import LineRenderer
import infernux_tween as api


@pytest.fixture
def line():
    scenes = SceneManager.instance()
    scene = scenes.create_scene('Paired color values')
    value = scene.create_game_object('Color line').add_component(LineRenderer)
    yield value
    api.clear(True)
    scenes.unload_scene(scene)


def colors():
    return (api.Color2([1, 0, 0, 1], [0, 1, 0, .5]),
            api.Color2([0, 0, 1, .5], [1, 0, 0, 1]))


def test_default_color_pair_has_independent_zero_fields_and_writable_channels():
    value = api.Color2()
    assert value.ca == value.cb == [0, 0, 0, 0]
    value.ca = [1, .1, .2, .3]
    value.ca[0] = .25
    assert value.ca == [float(np.float32(v)) for v in (.25, .1, .2, .3)]
    assert value.cb == [0, 0, 0, 0]


def test_color_pair_constructor_assignment_and_copies_own_their_field_values():
    source = [1, 0, 0, 1]
    value = api.Color2(ca=source, cb=source)
    source[0] = 9
    assert value.ca[0] == value.cb[0] == 1
    replacement = [0, 1, 0, .5]
    value.cb = replacement
    replacement[1] = 9
    for clone in (copy(value), deepcopy(value), pickle.loads(pickle.dumps(value))):
        clone.ca[0] = .25
        clone.cb[1] = .5
        assert value.ca[0] == 1 and value.cb[1] == 1
    assert value.ca is not value.cb


def test_color_pair_arithmetic_rounds_fields_and_scalar_parameter_to_float32():
    first = api.Color2([2**24, 0, 0, 1], [0, 0, 0, 0])
    second = api.Color2([1, 0, 0, 0], [0, 0, 0, 0])
    assert (first + second).ca[0] == 2**24
    assert (first * (1 + 2**-25)).ca[0] == 2**24


def test_color_pair_field_views_detach_on_replacement_and_pin_their_native_owner():
    value = api.Color2([1, 0, 0, 1], [0, 1, 0, .5])
    previous = value.ca
    value.ca = [0, 0, 1, 1]
    previous[0] = .25
    assert value.ca == [0, 0, 1, 1]
    retained = value.cb
    del value
    gc.collect()
    retained[1] = .25
    assert retained == list(retained._native.values) == [0, .25, 0, .5]


def test_line_timeline_captures_both_explicit_colors_at_creation(line):
    start, end = colors()
    handle = api.twn_color(line, start, end, 1.).set_ease(api.Ease.LINEAR).set_auto_kill(False)
    start.ca[0], start.cb[1], end.ca[2], end.cb[0] = 9, 9, 9, 9
    handle.goto(.5)
    assert line.start_color == [.5, 0, .5, .75]
    assert line.end_color == [.5, .5, 0, .75]


def test_line_manual_start_is_captured_before_later_caller_edits(line):
    start, end = colors()
    handle = api.twn_color(line, start, end, 1.).set_ease(api.Ease.LINEAR).set_auto_kill(False)
    explicit = api.Color2([.25, .5, .75, 1], [.5, .25, 0, .75])
    handle.from_(from_value=explicit, set_immediately=False, is_relative=False)
    explicit.ca[0], explicit.cb[1] = 9, 9
    handle.goto(.5)
    assert line.start_color == [.125, .25, .875, .75]
    assert line.end_color == [.75, .125, 0, .875]


def test_line_speed_represents_normalized_color_transitions_per_second(line):
    start, end = colors()
    handle = api.twn_color(line, start, end, 2.).set_speed_based()
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    assert handle.duration(False) == .5
    handle.goto(.25)
    assert line.start_color == [.5, 0, .5, .75]
    assert line.end_color == [.5, .5, 0, .75]


def test_reentrant_color_edit_keeps_one_ease_call_per_sample_and_old_outer_values(line):
    start, end = colors()
    calls, edited = [], False
    handle = api.twn_color(line, start, end, 1.).set_auto_kill(False)
    def ease(time, duration, amplitude, period):
        nonlocal edited
        calls.append(time)
        if not edited:
            edited = True
            handle.change_end_value(api.Color2())
        return time / duration
    handle.set_ease(ease).force_init()
    handle.goto(.5)
    assert calls == [.5, 0.]
    assert line.start_color == [.5, 0, .5, .75]
    assert line.end_color == [.5, .5, 0, .75]
    handle.goto(.5)
    assert line.start_color == [.5, 0, 0, .5]
    assert line.end_color == [0, .5, 0, .25]


def test_native_pair_job_tracks_field_replacement_and_survives_recycling(line):
    api.set_tweens_capacity(20, 10)
    start, end = colors()
    handle = api.twn_color(line, start, end, 1.).set_ease(api.Ease.LINEAR).set_recyclable(True)
    handle.force_init()
    job = handle._numeric_job
    old = handle._start.ca
    handle._start.ca = [.25, .5, .75, 1.]
    assert handle._getter().ca == [1, 0, 0, 1]
    old[0] = 99
    times = np.array([0., .5, 1.], dtype=np.float64)
    output = np.empty((3, 8), dtype=np.float32)
    job.sample_into(times, output)
    assert list(output[0, :4]) == [.25, .5, .75, 1.]
    expected = output.copy()
    handle.kill()
    replacement = api.twn_color(line, api.Color2(), api.Color2([1]*4, [1]*4), 1.)
    assert replacement is handle
    replacement.set_ease(api.Ease.LINEAR).goto(.5)
    job.sample_into(times, output)
    assert np.array_equal(output, expected)
    assert line.start_color == line.end_color == [.5]*4
