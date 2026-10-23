import pytest

from infernux_tween import Ease, TweenManager, UpdateType


def test_paused_or_completed_tweens_unregister_the_engine_phase():
    activity, value = [], [0.0]
    manager = TweenManager(lambda phase, enabled: activity.append((phase, enabled)))
    tween = manager.To(lambda: value[0], lambda v: value.__setitem__(0, v), 1.0, 1.0).SetAutoKill(False)
    tween.Pause()
    assert activity == [(UpdateType.Normal, True), (UpdateType.Normal, False)]
    manager.Update(1)
    assert value[0] == 0
    tween.Play()
    manager.Update(1)
    assert value[0] == 1
    assert activity[-1] == (UpdateType.Normal, False)
    tween.Restart()
    manager.Update(0.5)
    assert 0 < value[0] < 1


def test_complete_fires_once_with_or_without_internal_callbacks():
    for with_callbacks in (True, False):
        manager, events = TweenManager(), []
        child = manager.To(lambda: 0, lambda v: None, 1, 1)
        sequence = manager.Sequence().Append(child).SetAutoKill(False)
        sequence.AppendCallback(lambda: events.append("inside"))
        sequence.OnComplete(lambda: events.append("complete"))
        sequence.Complete(with_callbacks=with_callbacks)
        sequence.Complete(with_callbacks=with_callbacks)
        assert events == (["inside", "complete"] if with_callbacks else ["complete"])


def test_restart_from_complete_callback_keeps_the_tween_alive():
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda v: value.__setitem__(0, v), 1.0, 1.0).SetEase(Ease.Linear)
    tween.OnComplete(lambda: tween.Restart())
    manager.Update(1)
    assert tween.IsActive() and tween.IsPlaying()
    manager.Update(0.5)
    assert value[0] == 0.5
    for with_callbacks in (False, True):
        tween.Complete(with_callbacks=with_callbacks)
        assert tween.IsActive() and tween.IsPlaying()
        manager.Update(0.5)
        assert value[0] == 0.5


def test_start_callback_seek_replaces_the_original_frame_sample():
    for action in ("Rewind", "Restart"):
        manager, value, events = TweenManager(), [0.0], []
        tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1)
        tween.SetEase(Ease.Linear).OnStart(lambda: getattr(tween, action)())
        tween.OnPlay(lambda: events.append("play"))
        manager.Update(0.5)
        assert tween.IsActive() and tween.Elapsed() == 0 and value[0] == 0
        assert tween.IsPlaying() == (action == "Restart")
        assert events == (["play"] if action == "Restart" else [])
        tween.Play()
        manager.Update(0.25)
        assert value[0] == 2.5 and events == ["play"]


def test_target_and_id_controls_ignore_nested_tweens_and_allow_callback_mutation():
    manager, target, other = TweenManager(), object(), object()
    first = manager.To(lambda: 0.0, lambda value: None, 1.0, 1).SetTarget(target).SetId("menu")
    second = manager.To(lambda: 0.0, lambda value: None, 1.0, 1).SetTarget(target).SetId("menu")
    child = manager.To(lambda: 0.0, lambda value: None, 1.0, 1).SetTarget(other).SetId("menu")
    sequence = manager.Sequence().Append(child).SetTarget(other)
    assert manager.TotalActiveTweens() == manager.TotalPlayingTweens() == 3
    assert manager.Pause("menu") == 2
    assert not manager.IsTweening(target, also_check_if_playing=True)
    assert manager.TweensByTarget(target) == [first, second]
    assert manager.TweensById("menu", playing_only=True) == []
    assert sequence.IsPlaying()
    assert manager.Play(target) == 2
    assert manager.Goto(target, 0.25) == 2
    assert first.position == second.position == 0.25
    first.OnKill(lambda: second.Kill())
    assert manager.Kill(target) == 2
    assert manager.TotalActiveTweens() == 1
    assert manager.Complete(other) == 1 and not sequence.IsActive()
    assert not manager.IsTweening(other)


@pytest.mark.parametrize("auto_kill", (True, False))
@pytest.mark.parametrize("complete", (False, True))
def test_completion_pauses_only_a_retained_tween(auto_kill, complete):
    manager, events = TweenManager(), []
    tween = manager.To(lambda: 0.0, lambda value: None, 1.0, 1).SetAutoKill(auto_kill)
    tween.OnComplete(lambda: events.append("complete"))
    tween.OnPause(lambda: events.append("pause")).OnKill(lambda: events.append("kill"))
    tween.Complete() if complete else manager.Update(1)
    assert events == ["complete", "kill" if auto_kill else "pause"]


def test_running_tween_can_change_clock_while_nested_clock_is_owned_by_its_root():
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 1.0, 1).SetEase(Ease.Linear)
    manager.Update(0.25)
    tween.SetUpdate(UpdateType.Late, independent=True)
    manager.Update(0.25)
    assert value[0] == 0.25
    manager.Update(0, 0.25, UpdateType.Late)
    assert value[0] == 0.5
    tween.SetUpdate(UpdateType.Manual)
    manager.ManualUpdate(0.5, 0.5)
    assert value[0] == 1 and not tween.IsActive()
    child = manager.To(lambda: 0.0, lambda value: None, 1.0, 1)
    root = manager.Sequence().Append(child)
    child.SetUpdate(UpdateType.Manual)
    assert child.update_type == UpdateType.Normal and root.IsPlaying()
    manager.Clear()
    value[0] = 0.0
    controller = manager.To(lambda: 0.0, lambda value: None, 1.0, 1)
    switched = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 1.0, 1).SetEase(Ease.Linear)
    controller.OnUpdate(lambda: switched.SetUpdate(UpdateType.Manual))
    manager.Update(0.25)
    assert value[0] == 0
    manager.ManualUpdate(0.25, 0.25)
    assert value[0] == 0.25
