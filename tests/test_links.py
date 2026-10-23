import pytest

from infernux.lib import SceneManager
from infernux.components._component_lifecycle import RuntimeExecutionScheduler
from infernux_tween import Ease, LinkBehaviour, TweenManager
import infernux_tween as tween
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
    try:
        yield scene, obj
    finally:
        tween.clear()
        manager.unload_scene(scene)
        manager.stop()
        manager.clear_runtime_lifecycle_callbacks()
        scheduler.clear()
        scheduler.unbind_native_bridge()


def test_paused_tween_is_killed_by_native_owner_destruction_without_an_update(owner):
    scene, obj = owner
    SceneManager.instance().play()
    manager = TweenManager()
    tween = manager.to(lambda: 0.0, lambda value: None, 10, 1).pause().set_link(obj)
    assert not manager.total_playing_tweens()
    scene.destroy_game_object(obj)
    scene.process_pending_destroys()
    assert not tween.is_active() and manager.total_active_tweens() == 0


def test_pool_link_pauses_resumes_and_root_sequence_owns_its_children(owner):
    _, obj = owner
    SceneManager.instance().play()
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 10.0, 1).set_ease(Ease.LINEAR)
    tween.set_link(obj, LinkBehaviour.PAUSE_ON_DISABLE_PLAY_ON_ENABLE)
    link = obj.get_component(TweenLink)
    manager.update(0.25)
    obj.active = False
    manager.update(3)
    assert value[0] == 2.5 and not tween.is_playing()
    obj.active = True
    manager.update(0.25)
    assert value[0] == 5
    sequence = manager.sequence()
    with pytest.raises(ValueError, match="unstarted"):
        sequence.append(tween)
    fresh = manager.to(lambda: value[0], lambda item: value.__setitem__(0, item), 20.0, 1).set_link(obj)
    sequence.append(fresh).set_link(obj)
    assert fresh not in link._entries and sequence in link._entries
    sequence.kill()
    tween.kill()
    assert not link._entries
