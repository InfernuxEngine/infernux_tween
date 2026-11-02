"""Rewind requests distinguish state changes from repeat command notifications."""
import pytest

import infernux_tween as tween
from infernux_tween import Ease, RewindCallbackMode as Mode, TweenManager


def make_tween(manager):
    values, events = [0.0], []
    handle = manager.to(lambda: values[0], lambda x: values.__setitem__(0, x), 1.0, 1)
    handle.set_ease(Ease.LINEAR).set_auto_kill(False)
    handle.on_rewind(lambda: events.append("rewind"))
    handle.on_pause(lambda: events.append("pause"))
    handle.force_init()
    return handle, values, events


@pytest.mark.parametrize("mode,counts", [
    (Mode.FIRE_IF_POSITION_CHANGED, [0, 0, 0, 0]),
    (Mode.FIRE_ALWAYS_WITH_REWIND, [1, 2, 2, 2]),
    (Mode.FIRE_ALWAYS, [1, 2, 3, 4]),
])
def test_repeated_commands_follow_selected_policy_without_spurious_pause(mode, counts):
    manager = TweenManager()
    manager.rewind_callback_mode = mode
    handle, _, events = make_tween(manager)
    try:
        for command, count in zip((handle.rewind, handle.rewind, handle.play_backwards, handle.smooth_rewind), counts):
            command()
            assert events == ["rewind"] * count
            assert not handle.is_playing()
    finally:
        manager.clear()


@pytest.mark.parametrize("mode", list(Mode))
def test_returning_from_motion_notifies_once_for_every_policy(mode):
    manager = TweenManager()
    manager.rewind_callback_mode = mode
    handle, values, events = make_tween(manager)
    try:
        manager.update(.75)
        handle.play_backwards()
        manager.update(.75)
        assert values == [0.] and events == ["rewind", "pause"]
        manager.update(1)
        assert events == ["rewind", "pause"]
    finally:
        manager.clear()


@pytest.mark.parametrize("include_delay,expected", [(False, .25), (True, 0.)])
def test_rewind_at_start_applies_delay_choice_before_resuming(include_delay, expected):
    manager = TweenManager()
    handle, values, _ = make_tween(manager)
    handle.set_delay(.5)
    try:
        manager.update(.25)
        handle.rewind(include_delay)
        handle.play()
        manager.update(.25)
        assert values == [expected]
    finally:
        manager.clear()


def test_repeat_backwards_callback_observes_previous_direction_and_current_request():
    manager = TweenManager()
    manager.rewind_callback_mode = Mode.FIRE_ALWAYS
    handle, _, _ = make_tween(manager)
    observed = []
    handle.on_rewind(lambda: observed.append((handle.is_backwards(), handle.is_playing())))
    try:
        handle.play_backwards()
        assert observed == [(False, True)] and handle.is_backwards()
        handle.smooth_rewind()
        assert observed[-1] == (True, False)
    finally:
        manager.clear()


def test_module_policy_is_live_for_existing_handles_and_reset_with_manager(monkeypatch):
    manager = TweenManager()
    monkeypatch.setattr(tween, "_default_manager", manager)
    handle, _, events = make_tween(manager)
    tween.rewind_callback_mode = Mode.FIRE_ALWAYS_WITH_REWIND
    assert manager.rewind_callback_mode is Mode.FIRE_ALWAYS_WITH_REWIND
    assert "rewind_callback_mode" in dir(tween)
    try:
        handle.rewind()
        assert events == ["rewind"]
        tween.rewind_callback_mode = Mode.FIRE_IF_POSITION_CHANGED
        handle.rewind()
        assert events == ["rewind"]
    finally:
        manager.clear(True)
    assert tween.rewind_callback_mode is Mode.FIRE_IF_POSITION_CHANGED


def test_group_rewind_uses_each_root_policy_without_rewinding_nested_children_twice():
    manager = TweenManager()
    manager.rewind_callback_mode = Mode.FIRE_ALWAYS_WITH_REWIND
    child, _, child_events = make_tween(manager)
    root = manager.sequence().append(child).set_id("door").set_auto_kill(False)
    events = []
    root.on_rewind(lambda: events.append("root"))
    root.force_init()
    try:
        assert manager.rewind("door") == 1
        assert events == ["root"] and child_events == []
    finally:
        manager.clear()
