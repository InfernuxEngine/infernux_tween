"""The real plugin preloader registers and drives all engine update phases."""

from types import SimpleNamespace

import infernux_tween as api
from infernux_tween import Ease, TweenManager, UpdateType
from runtime.TweenPreload import TweenPreload


def test_preload_registers_callbacks_before_activity_and_releases_them(monkeypatch):
    manager = TweenManager()
    monkeypatch.setattr(api, "_default_manager", manager)
    phases, cleanups, libraries = {}, {}, []

    def add_update(callback, *, phase, enabled):
        registration = SimpleNamespace(callback=callback, enabled=enabled)
        phases[phase] = registration
        return registration

    context = SimpleNamespace(
        own_python_library=libraries.append,
        add_update=add_update,
        add_cleanup=lambda callback: cleanups.setdefault("cleanup", callback),
    )
    TweenPreload().preload(context)
    try:
        assert libraries == ["runtime/infernux_tween"]
        assert set(phases) == {"update", "late_update", "fixed_update"}
        assert all(not registration.enabled for registration in phases.values())
        state = [0.0]
        tween = manager.to(
            lambda: state[0], lambda value: state.__setitem__(0, value), 1.0, 1
        ).set_ease(Ease.LINEAR)
        assert phases["update"].enabled
        phases["update"].callback(0.5)
        assert state[0] == 0.5
        tween.set_update(UpdateType.LATE)
        assert phases["update"].enabled and phases["late_update"].enabled
        phases["late_update"].callback(0.5)
        assert state[0] == 1
    finally:
        cleanups["cleanup"]()
    assert manager._on_activity is None
    assert all(not registration.enabled for registration in phases.values())
