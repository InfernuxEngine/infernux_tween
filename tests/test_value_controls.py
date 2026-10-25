import asyncio

import pytest

from infernux.lib import Vector3
from infernux_tween import AxisConstraint, Ease, LoopType, TweenManager


def test_speed_based_capture_and_zero_distance():
    manager, value = TweenManager(), [(1.0, 2.0)]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), (4, 6), 2).set_speed_based().set_ease(Ease.LINEAR)
    manager.update(1)
    assert value[0] == pytest.approx((2.2, 3.6))
    assert tween.duration() == 2.5
    manager.update(1.5)
    assert value[0] == (4, 6) and not tween.is_active()
    still = manager.to(lambda: 4.0, lambda item: None, 4.0, 3).set_speed_based()
    manager.update(0.01)
    assert not still.is_active()


def test_integer_and_constrained_native_vector_keep_external_axes():
    manager, integer, vector = TweenManager(), [1], [Vector3(2, 3, 4)]
    manager.to(lambda: integer[0], lambda value: integer.__setitem__(0, value), 6, 1).set_ease(Ease.LINEAR)
    tween = manager.to(lambda: vector[0], lambda value: vector.__setitem__(0, value), Vector3(8, 10, 12), 1)
    tween.set_ease(Ease.LINEAR).set_options(AxisConstraint.Y, snapping=True)
    vector[0] = Vector3(20, 3, 40)
    manager.update(0.5)
    assert integer[0] == 4 and type(integer[0]) is int
    assert tuple(vector[0]) == (20, 6, 40)


def test_smooth_rewind_skips_restart_loops_and_preserves_yoyo_pose():
    for kind in (LoopType.RESTART, LoopType.YOYO):
        manager, value = TweenManager(), [0.0]
        tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).set_ease(Ease.LINEAR)
        tween.set_loops(4, kind).set_auto_kill(False)
        manager.update(1.25)
        previous = value[0]
        tween.smooth_rewind()
        assert value[0] == pytest.approx(previous)
        manager.update(1)
        assert value[0] == 0 and not tween.is_playing()


def test_coroutine_and_async_waits_keep_user_callbacks_and_release_on_kill():
    async def scenario():
        manager, value, events = TweenManager(), [0.0], []
        tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1)
        tween.set_delay(0.2).set_loops(2).set_auto_kill(False).on_complete(lambda: events.append("done"))
        start = tween.wait_for_start()
        position = asyncio.create_task(tween.async_wait_for_position(0.5))
        complete = asyncio.create_task(tween.async_wait_for_completion())
        killed = asyncio.create_task(tween.async_wait_for_kill())
        await asyncio.sleep(0)
        assert not start._is_ready()
        manager.update(0.75)
        await asyncio.sleep(0)
        assert start._is_ready() and position.done() and not complete.done()
        manager.update(1.5)
        await complete
        assert events == ["done"] and not killed.done()
        tween.kill()
        await killed
        assert not tween._waiters
    asyncio.run(scenario())


def test_diagnostics_count_roots_and_distinguish_paused_and_manual_clocks():
    from infernux_tween import UpdateType
    manager = TweenManager()
    manager.sequence().append(manager.to(lambda: 0, lambda value: None, 1, 1))
    manual = manager.to(lambda: 0, lambda value: None, 1, 1).set_update(UpdateType.MANUAL).pause()
    diagnostics = manager.get_diagnostics()
    assert diagnostics['active'] == 2 and diagnostics['playing'] == 1
    assert diagnostics['phases']['NORMAL'] == {'active': 1, 'playing': 1}
    assert diagnostics['phases']['MANUAL'] == {'active': 1, 'playing': 0}
    manual.play()
    manager.manual_update(1, 1)
    assert manager.get_diagnostics()['active'] == 1
    manager.clear()


def test_explicit_relative_from_captures_both_endpoints_before_delayed_playback():
    manager, value = TweenManager(), [(10.0, 20.0)]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), (20.0, 40.0), 1)
    tween.from_((5.0, 6.0), set_immediately=False, is_relative=True).set_delay(0.2).set_ease(Ease.LINEAR)
    assert value[0] == (10, 20)
    value[0] = (100.0, 200.0)
    manager.update(0.1)
    assert value[0] == (100, 200)
    manager.update(0.1)
    assert value[0] == (15, 26)
    manager.update(0.5)
    assert value[0] == pytest.approx((22.5, 43))


def test_explicit_numeric_from_retains_float_sampling_and_can_configure_speed_after_capture():
    manager, value = TweenManager(), [10.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 5)
    tween.from_(5).set_speed_based().set_ease(Ease.LINEAR)
    assert value[0] == pytest.approx(5)
    tween.force_init().force_init()
    assert tween.duration() == pytest.approx(3)
    manager.update(0.1)
    assert value[0] == pytest.approx(5.5)


def test_from_without_an_explicit_start_can_defer_target_capture_until_playback():
    manager, value = TweenManager(), [10.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 1)
    tween.from_(set_immediately=False, is_relative=False).set_delay(1).set_ease(Ease.LINEAR)
    value[0] = 30.0
    manager.update(1.5)
    assert value[0] == pytest.approx(25)


@pytest.mark.parametrize("state", ["playing", "paused", "backwards"])
def test_change_values_rewinds_without_replaying_delay_or_start_callbacks(state):
    manager, value, events = TweenManager(), [0.0], []
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1)
    tween.set_delay(0.5).set_ease(Ease.LINEAR).set_auto_kill(False)
    tween.on_start(lambda: events.append("start")).on_play(lambda: events.append("play"))
    tween.on_rewind(lambda: events.append("rewind"))
    manager.update(0.75)
    if state == "paused":
        tween.pause()
    elif state == "backwards":
        tween.play_backwards()
    tween.change_end_value(30.0, 2, snap_start_value=True)
    assert value[0] == 2.5 and tween.position == 0.5 and tween.duration() == 2
    assert tween.is_playing() == (state == "playing")
    assert tween.is_backwards() == (state == "backwards")
    manager.update(0.2)
    assert value[0] == pytest.approx(5.25 if state == "playing" else 2.5)
    tween.change_start_value(5.0, 0)
    assert value[0] == 5 and tween.duration() == 2
    tween.change_values(2.0, 6.0, 1)
    assert value[0] == 2 and tween.duration() == 1
    assert events.count("start") == events.count("play") == 1
    assert "rewind" in events


def test_change_start_before_initialization_uses_the_new_relative_base_and_keeps_partial_delay():
    manager, value = TweenManager(), [10.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 1)
    tween.set_relative().set_delay(1).set_ease(Ease.LINEAR)
    manager.update(0.3)
    tween.change_start_value(5.0)
    assert tween.position == pytest.approx(0.3) and value[0] == 5
    manager.update(0.7)
    assert value[0] == pytest.approx(5)
    manager.update(0.5)
    assert value[0] == pytest.approx(15)


def test_change_speed_based_duration_is_recomputed_only_for_a_new_positive_speed():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 2)
    tween.set_speed_based().set_ease(Ease.LINEAR).set_auto_kill(False)
    manager.update(1)
    tween.change_end_value(20.0)
    assert tween.duration() == 5
    tween.change_end_value(30.0, 3)
    assert tween.duration() == 10
    tween.change_values(10.0, 20.0, 2)
    assert tween.duration() == 5
    tween.force_init()
    assert tween.duration() == 5


def test_change_methods_leave_sequence_children_and_parent_timing_unchanged():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).set_ease(Ease.LINEAR)
    sequence = manager.sequence().append(tween)
    tween.change_start_value(50).change_end_value(100, 4).change_values(50, 100, 5)
    assert sequence.duration() == 1
    manager.update(0.5)
    assert value[0] == 5


def test_change_inside_an_update_callback_aborts_the_old_sample_and_respects_rewind_pause():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).set_ease(Ease.LINEAR)
    tween.on_update(lambda: tween.change_values(20.0, 30.0)).on_rewind(tween.pause)
    manager.update(0.5)
    assert tween.position == 0 and value[0] == 20 and not tween.is_playing()


def test_change_end_boolean_argument_snaps_start_without_replacing_duration():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 2).set_ease(Ease.LINEAR)
    manager.update(1)
    tween.change_end_value(20.0, True)
    assert value[0] == 5 and tween.duration() == 2 and tween.is_playing()
    manager.update(1)
    assert value[0] == pytest.approx(12.5)


def test_typed_options_distinguish_color_alpha_vector_axes_and_real_vector4():
    from infernux.lib import vec4f
    assert [int(axis) for axis in AxisConstraint] == [2, 4, 8, 16]
    manager = TweenManager()
    color, vector, vector4 = [[0.2, 0.3, 0.4, 0.5]], [Vector3(1, 2, 3)], [vec4f(1, 2, 3, 4)]
    manager.to(lambda: color[0], lambda v: color.__setitem__(0, v), [1., 1., 1., 1.], 1).set_options(True).set_ease(Ease.LINEAR)
    manager.to(lambda: vector[0], lambda v: vector.__setitem__(0, v), Vector3(10, 20, 30), 1).set_options(AxisConstraint(4), True).set_ease(Ease.LINEAR)
    manager.to(lambda: vector4[0], lambda v: vector4.__setitem__(0, v), vec4f(10, 20, 30, 40), 1).set_options(AxisConstraint(16)).set_ease(Ease.LINEAR)
    manager.update(0.5)
    assert color[0] == pytest.approx([0.2, 0.3, 0.4, 0.75])
    assert tuple(vector[0]) == (1, 11, 3)
    assert tuple(vector4[0]) == (1, 2, 3, 22)
    manager.clear()


def test_from_boolean_overloads_and_native_color_alpha_and_vector_uniform_start():
    for arguments, expected_immediate, expected_half in (((False,), 20, 15), ((True,), 30, 20), ((False, False), 10, 25), ((False, True), 10, 40)):
        manager, value = TweenManager(), [10.0]
        tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 20.0, 1).set_ease(Ease.LINEAR)
        tween.from_(*arguments)
        assert value[0] == expected_immediate
        if len(arguments) == 2:
            value[0] = 30
        manager.update(0.5)
        assert value[0] == expected_half
        manager.clear()
    manager, color, vector = TweenManager(), [[0.2, 0.3, 0.4, 0.5]], [Vector3(1, 2, 3)]
    manager.to(lambda: color[0], lambda v: color.__setitem__(0, v), [1., 1., 1., 1.], 1).from_(from_alpha_value=0.0).set_ease(Ease.LINEAR)
    manager.to(lambda: vector[0], lambda v: vector.__setitem__(0, v), Vector3(10, 20, 30), 1).from_(5.0).set_ease(Ease.LINEAR)
    assert color[0] == pytest.approx([0.2, 0.3, 0.4, 0]) and tuple(vector[0]) == (5, 5, 5)
    manager.update(0.5)
    assert color[0] == pytest.approx([0.2, 0.3, 0.4, 0.5]) and tuple(vector[0]) == (7.5, 12.5, 17.5)
    manager.clear()


def test_factory_virtual_axis_alpha_and_array_keep_their_distinct_value_contracts():
    manager, virtual = TweenManager(), []
    vector, color, route = [Vector3(1, 2, 3)], [[0.1, 0.2, 0.3, 0.4]], [Vector3(0, 0, 0)]
    manager.to(virtual.append, 2.0, 10.0, 2).set_ease(Ease.LINEAR)
    manager.to_axis(lambda: vector[0], lambda v: vector.__setitem__(0, v), 8, 2).set_ease(Ease.LINEAR)
    manager.to_alpha(lambda: color[0], lambda v: color.__setitem__(0, v), 1, 2).set_ease(Ease.LINEAR)
    segment = manager.to_array(lambda: route[0], lambda v: route.__setitem__(0, v), [Vector3(10, 0, 0), Vector3(10, 10, 0)], [1., 3.]).set_ease(Ease.OUT_QUAD)
    manager.update(0.5)
    assert virtual[-1] == 4 and tuple(vector[0]) == (2.75, 2, 3)
    assert color[0] == pytest.approx([0.1, 0.2, 0.3, 0.55]) and tuple(route[0]) == (7.5, 0, 0)
    manager.update(2)
    assert tuple(route[0]) == (10, 7.5, 0) and segment.duration() == 4
    manager.clear()
    route[0] = Vector3(0, 0, 0)
    segment = manager.to_array(lambda: route[0], lambda v: route.__setitem__(0, v), [Vector3(10, 0, 0), Vector3(10, 10, 0)], [5., 2.]).set_speed_based().set_ease(Ease.LINEAR)
    segment.force_init()
    assert segment.duration() == 7
    manager.update(2)
    assert tuple(route[0]) == (10, 0, 0)
    manager.clear()
    route[0] = Vector3(0, 0, 0)
    segment = manager.to_array(lambda: route[0], lambda v: route.__setitem__(0, v), [Vector3(10, 0, 0), Vector3(10, 10, 0)], [1., 1.]).set_ease(Ease.LINEAR).set_auto_kill(False)
    segment.change_values([Vector3(2, 0, 0), Vector3(12, 0, 0)], [Vector3(12, 0, 0), Vector3(12, 10, 0)], 2)
    manager.update(1.5)
    assert tuple(route[0]) == (12, 5, 0)
    segment.change_end_value([Vector3(20, 0, 0), Vector3(20, 10, 0)], snap_start_value=True)
    assert tuple(route[0]) == (12, 5, 0)
    manager.update(0.5)
    assert tuple(route[0]) == (16, 2.5, 0)
    manager.clear()


def test_native_quaternion_generic_euler_and_world_local_axis_rotation():
    from infernux.lib import quatf
    from infernux_tween.rotation import EulerTweener, RotateMode
    manager = TweenManager()
    initial = quatf.euler(0, 35, 0)
    world, local, shortest, long = [initial], [initial], [quatf.euler(0, 0, 0)], [quatf.euler(0, 0, 0)]
    half, relative = [quatf.euler(0, 0, 0)], [quatf.euler(0, 0, 0)]
    for value, mode in ((world, RotateMode.WORLD_AXIS_ADD), (local, RotateMode.LOCAL_AXIS_ADD)):
        manager.add(EulerTweener(lambda value=value: value[0], lambda v, value=value: value.__setitem__(0, v), Vector3(90, 0, 0), 1, mode)).set_ease(Ease.LINEAR)
    manager.to(lambda: shortest[0], lambda v: shortest.__setitem__(0, v), Vector3(0, 0, 360), 1).set_options(True).set_ease(Ease.LINEAR)
    manager.to(lambda: long[0], lambda v: long.__setitem__(0, v), Vector3(0, 0, 360), 1).set_options(use_shortest360_route=False).set_ease(Ease.LINEAR)
    manager.add(EulerTweener(lambda: half[0], lambda v: half.__setitem__(0, v), Vector3(0, 0, 180), 1)).set_ease(Ease.LINEAR)
    manager.add(EulerTweener(lambda: relative[0], lambda v: relative.__setitem__(0, v), Vector3(0, 0, 360), 1)).set_relative().set_ease(Ease.LINEAR)
    manager.update(0.5)
    assert quatf.angle(world[0], quatf.euler(45, 0, 0) * initial) < 0.05
    assert quatf.angle(local[0], initial * quatf.euler(45, 0, 0)) < 0.05
    assert quatf.angle(shortest[0], quatf.euler(0, 0, 0)) < 0.05
    assert quatf.angle(long[0], quatf.euler(0, 0, 180)) < 0.05
    assert quatf.angle(half[0], quatf.euler(0, 0, 90)) < 0.05
    assert quatf.angle(relative[0], quatf.euler(0, 0, 180)) < 0.05
    manager.clear()


def test_settings_queries_fillable_lists_and_combined_target_id_controls():
    from infernux_tween.core import TweenParams, UpdateType
    manager, target, value = TweenManager(), object(), [0.0]
    params = TweenParams().set_id('shared').set_loops(2, LoopType.YOYO).set_delay(0.5).set_ease(Ease.LINEAR)
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1).set_target(target).set_as(params).set_auto_kill(False)
    tween.force_init().set_loops(3)
    assert tween.is_initialized() and tween.loop_type is LoopType.YOYO and tween.loops() == 3
    manager.update(0.25)
    assert tween.delay() == 0.5 and tween.elapsed_delay() == 0.25 and tween.elapsed() == 0
    supplied = ['old']
    assert manager.tweens_by_id('shared', fillable_list=supplied) is supplied and supplied == [tween]
    assert manager.pause(target) == 1 and manager.pause(target) == 0
    assert manager.play(target=target, id='other') == 0 and manager.play(target=target, id='shared') == 1
    assert manager.total_tweens_by_id('shared') == manager.total_active_tweeners() == 1
    assert manager.total_active_sequences() == 0
    manager.restart(target, 'shared', False, 0.2)
    assert tween.delay() == 0.2 and tween.elapsed() == 0
    manager.default_update_type, manager.default_time_scale_independent = UpdateType.LATE, True
    tween.set_update(True)
    assert tween.update_type is UpdateType.LATE and tween.is_time_scale_independent()
    manager.update(0, 0.5, UpdateType.LATE)
    assert value[0] == pytest.approx(5)
    assert manager.kill(target=target, id='shared') == 1
    assert tween.duration() == tween.loops() == tween.elapsed() == 0 and not tween.is_initialized()
    assert manager.tweens_by_id('shared') is None
    assert manager.tweens_by_id('shared', fillable_list=supplied) is supplied and supplied == []
    manager.clear(True)
    assert manager.default_update_type is UpdateType.NORMAL and not manager.default_time_scale_independent


def test_play_controls_respect_endpoints_direction_and_affected_counts():
    manager, value, events = TweenManager(), [0.0], []
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1)
    tween.set_ease(Ease.LINEAR).set_auto_kill(False).set_id('move')
    tween.on_play(lambda: events.append('play'))
    assert manager.play_backwards('move') == 0
    assert tween.is_backwards() and not tween.is_playing()
    assert manager.play_all() == 0
    assert manager.play_forward('move') == 1
    assert manager.play_forward('move') == 0
    manager.update(1)
    assert value[0] == 10 and tween.is_complete()
    assert manager.play('move') == manager.play_forward_all() == manager.toggle_pause('move') == 0
    assert not tween.play().is_playing() and events == ['play']
    assert manager.play_backwards_all() == 1
    assert manager.play_backwards_all() == 0
    assert manager.play_forward_all() == 0
    assert not tween.is_backwards() and not tween.is_playing()
    assert manager.play_backwards_all() == 1
    manager.update(0.25)
    assert value[0] == 7.5
    assert manager.play_forward_all() == 1
    assert manager.play_forward_all() == 0
    manager.update(0.1)
    assert value[0] == pytest.approx(8.5)
    tween.rewind().play_backwards()
    assert not tween.is_playing() and manager.play_all() == 0
    tween.restart()
    assert tween.is_playing()
    manager.clear()


def test_tween_params_capture_defaults_and_keep_their_own_overloads(monkeypatch):
    import infernux_tween.core as core
    from infernux_tween import TweenParams, UpdateType
    defaults = TweenManager()
    defaults.default_auto_kill = False
    defaults.default_loop_type = LoopType.YOYO
    defaults.default_update_type, defaults.default_time_scale_independent = UpdateType.FIXED, True
    defaults.default_ease_overshoot_or_amplitude, defaults.default_ease_period = 2.75, 0.4
    monkeypatch.setattr(core, '_default_manager', defaults)
    params, manager, target, value = TweenParams(), TweenManager(), object(), [0.0]
    params.set_target(object()).set_loops(3, None)
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 1).set_target(target).set_as(params)
    assert tween.target is target and not tween.auto_kill
    assert tween.loop_type is LoopType.YOYO and tween.loops() == 3
    assert tween.update_type is UpdateType.FIXED and tween.independent
    assert tween._ease_args == (2.75, 0.4)
    params.set_update(UpdateType.LATE)
    tween.set_as(params)
    assert tween.update_type is UpdateType.LATE and not tween.independent
    params.set_update(True).set_ease(Ease.OUT_ELASTIC, period=0.2)
    tween.set_as(params)
    assert tween.update_type is UpdateType.FIXED and tween.independent
    assert tween._ease_args == (2.75, 0.2)
    params.set_ease(Ease.OUT_BACK, overshoot_or_amplitude=4)
    tween.set_as(params)
    assert tween._ease_args == (4, 0.4)
    params.set_ease(Ease.IN_ELASTIC, None, None)
    tween.set_as(params)
    assert tween._ease_args == (2.75, 0.4)
    params.clear().set_ease(custom_ease=lambda t, d, a, p: t/d)
    tween.set_as(params).goto(0.5)
    assert value[0] == 5 and params._settings.target is None
    assert tween.target is target and tween.loop_type is LoopType.YOYO
    manager.clear()


def test_done_completes_paused_or_delayed_zero_duration_roots_only():
    for delayed in (False, True):
        manager, value, events = TweenManager(), [0.0], []
        tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 0)
        tween.on_complete(lambda: events.append('complete')).pause()
        if delayed:
            tween.set_delay(2)
        tween.force_init()
        assert not tween.is_complete()
        assert tween.done() is tween
        assert value[0] == 10 and not tween.is_active() and events == ['complete']
        value = [0.0]
        child = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 10., 0)
        sequence = manager.sequence().append_interval(1).append(child)
        child.done()
        assert value[0] == 0 and child.is_active() and not child.is_initialized()
        manager.update(1)
        assert value[0] == 10 and not sequence.is_active()
