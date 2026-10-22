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
