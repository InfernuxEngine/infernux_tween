"""Clock selection, shared frame samples and the engine's native frame filter."""
from types import SimpleNamespace

import pytest
import infernux_tween as api
from infernux_tween import Ease, TweenManager, UpdateType
from infernux.timing import Time
import runtime.TweenPreload as preload_module


@pytest.fixture
def clocks(monkeypatch):
    manager, phases, cleanup = TweenManager(), {}, []
    monkeypatch.setattr(api, '_default_manager', manager)
    clock = SimpleNamespace(time_scale=.5, smooth_delta_time=.02, unscaled_delta_time=.5)
    monkeypatch.setattr(preload_module, 'Time', clock)

    def add_update(callback, *, phase, enabled):
        result = SimpleNamespace(callback=callback, enabled=enabled)
        phases[phase] = result
        return result

    preload_module.TweenPreload().preload(SimpleNamespace(own_python_library=lambda _: None,
        add_update=add_update, add_cleanup=cleanup.append))
    try:
        yield manager, clock, phases
    finally:
        for close in cleanup:
            close()


def make(manager, phase, independent=False):
    value = [0.]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 1., 1.)
    tween.set_ease(Ease.LINEAR).set_update(phase, independent)
    return tween, value


def test_late_samples_normal_clock_even_with_no_normal_animations(clocks):
    manager, clock, phases = clocks
    manager.use_smooth_delta_time, manager.max_smooth_unscaled_time = True, .1
    late, value = make(manager, UpdateType.LATE, True)
    assert phases['update'].enabled and phases['late_update'].enabled
    phases['update'].callback(.25)
    assert value[0] == 0
    clock.unscaled_delta_time = .9
    manager.max_smooth_unscaled_time = .01
    phases['late_update'].callback(.25)
    assert value[0] == pytest.approx(.1)
    late.kill()
    assert not phases['update'].enabled and not phases['late_update'].enabled


def test_smooth_fixed_clock_uses_scale_conversion_but_not_frame_unscaled_cap(clocks):
    manager, clock, phases = clocks
    manager.use_smooth_delta_time, manager.max_smooth_unscaled_time = True, .001
    regular, _ = make(manager, UpdateType.FIXED)
    independent, _ = make(manager, UpdateType.FIXED, True)
    phases['fixed_update'].callback(.03)
    assert regular.position == pytest.approx(.02)
    assert independent.position == pytest.approx(.04)
    clock.time_scale = 0
    phases['fixed_update'].callback(.03)
    assert regular.position == pytest.approx(.02)
    assert independent.position == pytest.approx(.04)


def test_manual_clocks_ignore_automatic_smoothing_options(clocks):
    manager, clock, phases = clocks
    manager.use_smooth_delta_time, manager.max_smooth_unscaled_time = True, .001
    regular, _ = make(manager, UpdateType.MANUAL)
    independent, _ = make(manager, UpdateType.MANUAL, True)
    manager.manual_update(.25, .5)
    assert regular.position == .25 and independent.position == .5


def test_module_clock_settings_forward_to_the_default_manager(clocks):
    manager, _, _ = clocks
    api.use_smooth_delta_time = True
    api.max_smooth_unscaled_time = .03
    assert manager.use_smooth_delta_time and manager.max_smooth_unscaled_time == 0.029999999329447746
    assert 'use_smooth_delta_time' in dir(api)


def test_native_game_clock_warmup_pause_decay_and_session_reset():
    Time._reset()
    try:
        assert Time.smooth_delta_time == 0
        Time._tick(.02)
        assert Time.smooth_delta_time == 0
        Time._tick(.01)
        assert Time.smooth_delta_time == pytest.approx(.01)
        Time._tick(.1)
        Time._tick(.02)
        assert Time.smooth_delta_time == pytest.approx(.05555556, abs=2e-8)
        for _ in range(128):
            Time._tick(.02)
        assert Time.smooth_delta_time == pytest.approx(.02)
        Time.time_scale = 0
        Time._tick(.5)
        assert Time.delta_time == 0 and 0 < Time.smooth_delta_time < .02
        # A physics sample does not advance this frame-based filter.
        frame_value = Time.smooth_delta_time
        Time._tick_fixed(.02)
        assert Time.smooth_delta_time == frame_value
        Time._reset()
        assert Time.smooth_delta_time == 0
        Time._tick(.001)
        assert Time.smooth_delta_time == 0
    finally:
        Time._reset()
