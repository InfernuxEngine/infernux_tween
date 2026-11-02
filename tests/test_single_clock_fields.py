"""Single-width clock storage is prepared at configuration boundaries."""
import struct
import pytest
import numpy as np
from infernux_tween import Ease, LoopType, TweenManager, TweenParams

f32 = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]


def test_clock_configuration_keeps_python_numbers_with_single_precision_storage():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda v: None, 1., 1.1).set_delay(.1)
        handle.time_scale = 1.1
        handle.ease_period = .4
        handle.ease_overshoot_or_amplitude = 2.1
        assert type(handle.duration(False)) is float and handle.duration(False) == f32(1.1)
        assert handle.delay() == f32(.1)
        assert handle.time_scale == f32(1.1)
        assert handle.ease_period == f32(.4)
        assert handle.ease_overshoot_or_amplitude == f32(2.1)
    finally:
        manager.clear()


@pytest.mark.parametrize('name', ['time_scale', 'unscaled_time_scale', 'max_smooth_unscaled_time',
                                  'default_ease_overshoot_or_amplitude', 'default_ease_period'])
def test_manager_single_fields_prepare_user_assignments(name):
    manager = TweenManager()
    setattr(manager, name, 1.1)
    assert getattr(manager, name) == f32(1.1)


def test_ease_and_settings_copies_share_prepared_parameters():
    manager = TweenManager()
    try:
        first = manager.to(lambda: 0., lambda v: None, 1., 1.).set_ease(Ease.OUT_BACK, 2.1, .4)
        first.time_scale = 1.1
        second = manager.to(lambda: 0., lambda v: None, 1., 1.).set_as(first)
        assert second.time_scale == f32(1.1)
        assert second.ease_overshoot_or_amplitude == f32(2.1) and second.ease_period == f32(.4)
        parameters = TweenParams().set_delay(.1).set_ease(Ease.OUT_BACK, 2.1, .4)
        third = manager.to(lambda: 0., lambda v: None, 1., 1.).set_as(parameters)
        assert third.delay() == f32(.1) and third.ease_period == f32(.4)
    finally:
        manager.clear()


def test_duration_edits_and_sequence_extents_store_single_width_results():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda v: None, 1., 1.)
        handle.change_end_value(2., 1.1)
        assert handle.duration(False) == f32(1.1)
        child = manager.to(lambda: 0., lambda v: None, 1., .1)
        root = manager.sequence().append(child).append_interval(.2)
        assert root.duration(False) == f32(f32(.1) + f32(.2))
        root.set_delay(.1, False).set_loops(3)
        assert root.duration() == f32(root.duration(False) * 3)
    finally:
        manager.clear()


def test_custom_easing_receives_single_arguments_and_returns_a_single_factor():
    manager, calls, values = TweenManager(), [], []
    try:
        manager.default_ease_overshoot_or_amplitude = 2.1
        manager.default_ease_period = .4
        def custom(*args):
            calls.append(args)
            return .1
        handle = manager.to(lambda: 0., values.append, 1., 1.1).set_ease(custom).set_auto_kill(False)
        handle.goto(.25)
        assert calls[-1] == (f32(.25), f32(1.1), f32(2.1), f32(.4))
        assert values[-1] == f32(.1)
    finally:
        manager.clear()


def test_loop_extent_converts_the_integer_count_before_multiplication():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda v: None, 1., 1.0000001192092896).set_loops(16777217)
        assert handle.duration() == 16777218.
    finally:
        manager.clear()


def test_duration_and_restart_sentinels_use_converted_single_values():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda v: None, 1., 1.).set_delay(.25)
        handle.change_end_value(2., 1e-46)
        assert handle.duration(False) == 1.
        handle.restart(change_delay_to=-1e-46)
        assert handle.delay() == 0.
    finally:
        manager.clear()


def test_underflowed_update_clock_does_not_start_the_tween():
    manager, events = TweenManager(), []
    try:
        handle = manager.to(lambda: 0., lambda v: None, 1., 1.).on_start(lambda: events.append('start'))
        manager.update(-1e-46)
        assert events == [] and not handle.is_initialized()
    finally:
        manager.clear()


@pytest.mark.parametrize('kind', [int, float, np.float32, np.float64,
                                  np.int32, np.int64,
                                  np.uint32, np.uint64])
def test_custom_scalar_sampling_keeps_types_and_freezes_values_before_callbacks(kind):
    manager, values = TweenManager(), []
    armed = False
    try:
        def custom(t, d, a, p):
            nonlocal armed
            if armed:
                armed = False
                handle.start_value = kind(10)
                handle.change_value = kind(20)
            return t / d
        handle = manager.to(lambda: kind(0), values.append, kind(8), 1.).set_ease(custom).set_auto_kill(False)
        handle.force_init()
        armed = True
        handle.goto(.5)
        assert type(values[-1]) is kind and values[-1] == 4
        handle.goto(.75)
        assert type(values[-1]) is kind and values[-1] == 25
    finally:
        manager.clear()


@pytest.mark.parametrize('mode', list(LoopType))
@pytest.mark.parametrize('loops', [3, 4])
@pytest.mark.parametrize('control', ['complete', 'goto', 'update'])
def test_rounded_loop_extent_publishes_the_last_cycle_endpoint(mode, loops, control):
    manager, values, completed = TweenManager(), [], []
    try:
        handle = manager.to(lambda: 0., values.append, 1., .1).set_ease(Ease.LINEAR)
        handle.set_delay(.25).set_loops(loops, mode).set_auto_kill(False)
        handle.on_complete(lambda: completed.append((handle.position, values[-1])))
        if control == 'update':
            manager.update(1.)
        elif control == 'goto':
            handle.goto(handle.duration())
        else:
            handle.complete()
        expected = float(loops) if mode == LoopType.INCREMENTAL else 0. if mode == LoopType.YOYO and loops % 2 == 0 else 1.
        assert handle.is_complete() and handle.completed_loops() == loops
        assert values[-1] == expected and handle.position == f32(.1)
        assert handle.elapsed(False) == f32(.1)
        assert completed == [(f32(.1), expected)]
    finally:
        manager.clear()
