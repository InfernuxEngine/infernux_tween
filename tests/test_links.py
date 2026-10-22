import pytest

from infernux.lib import SceneManager
from infernux.components._component_lifecycle import RuntimeExecutionScheduler
from infernux_tween import Ease, LinkBehaviour, TweenManager
from infernux_tween.link import TweenLink


@pytest.fixture
def owner():
    manager = SceneManager.instance()
    scheduler = RuntimeExecutionScheduler(name="plugin-links", native_bridge=True)
    manager.set_runtime_lifecycle_callbacks(
        scheduler.begin_native_frame,
        lambda dt: scheduler.execute_native_phase("fixed_update", dt),
        lambda dt: scheduler.execute_native_phase("update", dt),
        lambda dt: scheduler.execute_native_phase("late_update", dt),
        scheduler.execute_native_editor_update, scheduler.end_native_frame,
    )
    scheduler.bind_native_bridge(manager)
    scene = manager.create_scene("Tween link lifecycle")
    obj = scene.create_game_object("Pooled owner")
    yield scene, obj
    manager.unload_scene(scene)
    manager.clear_runtime_lifecycle_callbacks()
    scheduler.clear()
    scheduler.unbind_native_bridge()


def test_paused_tween_is_killed_by_native_owner_destruction_without_an_update(owner):
    scene, obj = owner
    manager = TweenManager()
    tween = manager.To(lambda: 0.0, lambda value: None, 10, 1).Pause().SetLink(obj)
    assert not manager.TotalPlayingTweens()
    scene.destroy_game_object(obj)
    scene.process_pending_destroys()
    assert not tween.IsActive() and manager.TotalActiveTweens() == 0


def test_pool_link_pauses_resumes_and_root_sequence_owns_its_children(owner):
    _, obj = owner
    manager, value = TweenManager(), [0.0]
    tween = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).SetEase(Ease.Linear)
    tween.SetLink(obj, LinkBehaviour.PauseOnDisablePlayOnEnable)
    link = obj.get_component(TweenLink)
    manager.Update(0.25)
    link.on_disable()
    manager.Update(3)
    assert value[0] == 2.5 and not tween.IsPlaying()
    link.on_enable()
    manager.Update(0.25)
    assert value[0] == 5
    sequence = manager.Sequence()
    with pytest.raises(ValueError, match="unstarted"):
        sequence.Append(tween)
    fresh = manager.To(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 1).SetLink(obj)
    sequence.Append(fresh).SetLink(obj)
    assert fresh not in link._entries and sequence in link._entries
    sequence.Kill()
    tween.Kill()
    assert not link._entries
