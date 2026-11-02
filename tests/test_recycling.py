import pytest

from infernux_tween import Ease, LogBehaviour, TweenManager, TweenParams


def test_initialized_pool_reuses_objects_and_resets_callbacks_targets_and_options():
    manager = TweenManager().init(True, True, LogBehaviour.ERRORS_ONLY).set_capacity(3, 1)
    first = manager.to(lambda: 0., lambda v: None, 10., 1).set_id("old").set_target(object())
    calls = []
    first.on_kill(lambda: calls.append("killed")).kill()
    assert calls == ["killed"] and manager.total_pooled_tweens() == 1
    assert not first.is_active() and first.target is None
    generation = first._generation
    second = manager.to(lambda: 2., lambda v: None, 8., 3)
    assert second is first and second._generation > generation
    assert second.id is None and second._callbacks == {} and second.duration() == 3
    second.kill()
    manager.clear_cached_tweens()
    assert manager.total_pooled_tweens() == 0


def test_recyclable_override_and_tween_params_are_real_settings():
    manager = TweenManager().init(True)
    value = manager.to(lambda: 0., lambda v: None, 1., 1).set_recyclable(False)
    value.kill()
    assert manager.total_pooled_tweens() == 0
    settings = TweenParams().set_recyclable(True)
    other = manager.to(lambda: 0., lambda v: None, 1., 1).set_as(settings)
    other.kill()
    assert manager.total_pooled_tweens() == 1


def test_nested_sequences_recycle_their_children_after_kill_callbacks_finish():
    manager = TweenManager().init(True)
    child = manager.to(lambda: 0., lambda v: None, 1., 1)
    nested = manager.sequence().append(child)
    parent = manager.sequence().append(nested)
    parent.kill()
    assert manager.total_pooled_tweens() == 3
    assert manager.total_active_tweens() == 0
    replacement = manager.sequence()
    assert replacement._entries == []
    manager.clear()
    assert manager.total_pooled_tweens() == 0


def test_recycled_object_created_by_a_callback_is_not_advanced_from_an_old_frame_entry():
    manager = TweenManager().init(True)
    first = manager.to(lambda: 0., lambda v: None, 1., 1)
    victim = manager.to(lambda: 0., lambda v: None, 1., 1)
    created = []
    def replace():
        first.on_update(lambda: None)
        victim.kill()
        created.append(manager.to(lambda: 0., lambda v: None, 1., 1))
    first.on_update(replace)
    manager.update(.25)
    assert created[0] is not victim and not victim.is_active()
    assert created[0].position == 0 and manager.total_pooled_tweens() == 1
    manager.update(.25)
    assert created[0].position == .25
    manager.clear()


def test_validate_and_safe_mode_retire_invalid_targets_and_preserve_other_tweens():
    manager = TweenManager()
    def invalid():
        raise RuntimeError("target retired")
    broken = manager.to(invalid, lambda v: None, 1., 1)
    valid = manager.to(lambda: 0., lambda v: None, 1., 1).set_auto_kill(False)
    assert manager.validate() == 1
    assert not broken.is_active() and valid.is_active()
    manager.to(invalid, lambda v: None, 1., 1)
    manager.update(.1)
    assert valid.position == pytest.approx(.1) and manager._safe_mode_errors == 1
    manager.clear()
    manager = TweenManager().init(use_safe_mode=False)
    manager.to(invalid, lambda v: None, 1., 1)
    with pytest.raises(RuntimeError, match="target retired"):
        manager.update(.1)


def test_capacity_configuration_is_early_and_clear_destroy_resets_initialization():
    manager = TweenManager().init(True).set_capacity(1, 2)
    assert len(manager._pool_storage["tweeners"]) == 2
    manager.to(lambda: 0., lambda v: None, 1., 1)
    with pytest.raises(RuntimeError):
        manager.set_tweens_capacity(4, 1)
    manager.clear(destroy=True)
    manager.init(False, False)
    assert not manager.default_recyclable and not manager.use_safe_mode


def test_safe_mode_callback_errors_do_not_abort_other_callbacks_or_playback():
    manager, events = TweenManager(), []
    def failed_callback():
        events.append("failed")
        raise RuntimeError("callback failure")
    sequence = manager.sequence().append_callback(failed_callback).append_interval(.5)
    sequence.append_callback(lambda: events.append("tail")).set_auto_kill(False)
    manager.update(.5)
    assert events == ["failed", "tail"]
    assert sequence.is_complete() and manager._safe_mode_errors == 1
    manager.clear()


def test_self_kill_inside_callback_keeps_the_new_tween_separate_until_retirement():
    manager, replacements = TweenManager().init(True), []
    original = manager.to(lambda: 0., lambda v: None, 1., 1)
    def replace_self():
        original.kill()
        replacements.append(manager.to(lambda: 0., lambda v: None, 2., 2))
    original.on_update(replace_self)
    manager.update(.25)
    assert replacements[0] is not original and not original.is_active()
    assert replacements[0].position == 0 and replacements[0].is_active()
    manager.update(.5)
    assert replacements[0].position == .5
    manager.clear()
