import pytest

from infernux_tween import Ease, TweenManager, UpdateType


def test_paused_or_completed_tweens_unregister_the_engine_phase():
    activity, value = [], [0.0]
    manager = TweenManager(lambda phase, enabled: activity.append((phase, enabled)))
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 1.0, 1.0).set_auto_kill(False)
    tween.pause()
    assert activity == [(UpdateType.NORMAL, True), (UpdateType.NORMAL, False)]
    manager.update(1)
    assert value[0] == 0
    tween.play()
    manager.update(1)
    assert value[0] == 1
    assert activity[-1] == (UpdateType.NORMAL, False)
    tween.restart()
    manager.update(0.5)
    assert 0 < value[0] < 1


def test_complete_fires_once_with_or_without_internal_callbacks():
    for with_callbacks in (True, False):
        manager, events = TweenManager(), []
        child = manager.to(lambda: 0, lambda v: None, 1, 1)
        sequence = manager.sequence().append(child).set_auto_kill(False)
        sequence.append_callback(lambda: events.append("inside"))
        sequence.on_complete(lambda: events.append("complete"))
        sequence.complete(with_callbacks=with_callbacks)
        sequence.complete(with_callbacks=with_callbacks)
        assert events == (["inside", "complete"] if with_callbacks else ["complete"])


def test_restart_from_complete_callback_keeps_the_tween_alive():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), 1.0, 1.0).set_ease(Ease.LINEAR)
    tween.on_complete(lambda: tween.restart())
    manager.update(1)
    assert tween.is_active() and tween.is_playing()
    manager.update(0.5)
    assert value[0] == 0.5
    for with_callbacks in (False, True):
        tween.complete(with_callbacks=with_callbacks)
        assert tween.is_active() and tween.is_playing()
        manager.update(0.5)
        assert value[0] == 0.5


def test_start_callback_seek_replaces_the_original_frame_sample():
    for action in ("rewind", "restart"):
        manager, value, events = TweenManager(), [0.0], []
        tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1)
        tween.set_ease(Ease.LINEAR).on_start(lambda: getattr(tween, action)())
        tween.on_play(lambda: events.append("play"))
        manager.update(0.5)
        assert tween.is_active() and tween.elapsed() == 0 and value[0] == 0
        assert tween.is_playing() == (action == "restart")
        assert events == (["play"] if action == "restart" else [])
        tween.play()
        manager.update(0.25)
        assert value[0] == 2.5 and events == ["play"]


def test_target_and_id_controls_ignore_nested_tweens_and_allow_callback_mutation():
    manager, target, other = TweenManager(), object(), object()
    first = manager.to(lambda: 0.0, lambda value: None, 1.0, 1).set_target(target).set_id("menu")
    second = manager.to(lambda: 0.0, lambda value: None, 1.0, 1).set_target(target).set_id("menu")
    child = manager.to(lambda: 0.0, lambda value: None, 1.0, 1).set_target(other).set_id("menu")
    sequence = manager.sequence().append(child).set_target(other)
    assert manager.total_active_tweens() == manager.total_playing_tweens() == 3
    assert manager.pause("menu") == 2
    assert not manager.is_tweening(target, also_check_if_is_playing=True)
    assert manager.tweens_by_target(target) == [first, second]
    assert manager.tweens_by_id("menu", playing_only=True) is None
    assert sequence.is_playing()
    assert manager.play(target) == 2
    assert manager.goto(target, 0.25) == 2
    assert first.position == second.position == 0.25
    first.on_kill(lambda: second.kill())
    assert manager.kill(target) == 2
    assert manager.total_active_tweens() == 1
    assert manager.complete(other) == 1 and not sequence.is_active()
    assert not manager.is_tweening(other)


@pytest.mark.parametrize("auto_kill", (True, False))
@pytest.mark.parametrize("complete", (False, True))
def test_completion_pauses_only_a_retained_tween(auto_kill, complete):
    manager, events = TweenManager(), []
    tween = manager.to(lambda: 0.0, lambda value: None, 1.0, 1).set_auto_kill(auto_kill)
    tween.on_complete(lambda: events.append("complete"))
    tween.on_pause(lambda: events.append("pause")).on_kill(lambda: events.append("kill"))
    tween.complete() if complete else manager.update(1)
    assert events == ["complete", "kill" if auto_kill else "pause"]


def test_running_tween_can_change_clock_while_nested_clock_is_owned_by_its_root():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 1.0, 1).set_ease(Ease.LINEAR)
    manager.update(0.25)
    tween.set_update(UpdateType.LATE, is_independent_update=True)
    manager.update(0.25)
    assert value[0] == 0.25
    manager.update(0, 0.25, UpdateType.LATE)
    assert value[0] == 0.5
    tween.set_update(UpdateType.MANUAL)
    manager.manual_update(0.5, 0.5)
    assert value[0] == 1 and not tween.is_active()
    child = manager.to(lambda: 0.0, lambda value: None, 1.0, 1)
    root = manager.sequence().append(child)
    child.set_update(UpdateType.MANUAL)
    assert child.update_type == UpdateType.NORMAL and root.is_playing()
    manager.clear()
    value[0] = 0.0
    controller = manager.to(lambda: 0.0, lambda value: None, 1.0, 1)
    switched = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 1.0, 1).set_ease(Ease.LINEAR)
    controller.on_update(lambda: switched.set_update(UpdateType.MANUAL))
    manager.update(0.25)
    assert value[0] == 0
    manager.manual_update(0.25, 0.25)
    assert value[0] == 0.25
