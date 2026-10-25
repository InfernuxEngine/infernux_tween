import pytest

from infernux.components import ComponentRef, InxComponent, serialized_field
from infernux.components.fields import get_raw_field_value
from infernux.lib import SceneManager, Vector3
from infernux.ui.ui_event_entry import UIEventArgument
from infernux_tween import Ease
import infernux_tween as tween_api
from infernux_tween.events import TweenCallback, invoke_callbacks
from runtime.TweenAnimation import TweenAnimation
from test_links import owner


class EventReceiver(InxComponent):
    count: int = serialized_field(default=0)

    def Record(self, amount: int):
        self.count += amount

    def KeywordOnly(self, *, amount: int):
        self.count += amount

    def Variadic(self, *amounts):
        self.count += sum(amounts)

    def VectorArgument(self, amount: Vector3):
        self.count += int(amount.x)

    def AmbiguousArgument(self, amount: int | str):
        pass

    def AddCallback(self):
        self.animation.on_start_entries.append(callback(self, 2))

    def RemoveCallback(self):
        self.animation.on_start_entries.pop(0)


def callback(receiver, amount):
    return TweenCallback(target=ComponentRef(receiver), method_name='Record',
                         arguments=[UIEventArgument(kind='int', name='amount', int_value=amount)])


def test_saved_callbacks_bind_the_exact_component_and_fire_once_per_transition(owner):
    _, obj = owner
    first, second = obj.add_component(EventReceiver), obj.add_component(EventReceiver)
    animation = obj.add_component(TweenAnimation)
    animation.auto_play, animation.auto_kill, animation.ease = False, False, Ease.LINEAR
    for name, amount in [('start', 1), ('complete', 10), ('rewind', 100), ('kill', 1000)]:
        saved = callback(second, amount)._serialize()
        restored = TweenCallback._deserialize(saved)
        assert get_raw_field_value(restored, 'target').component_id == second.component_id
        setattr(animation, 'on_'+name+'_entries', [restored])
    script_events = []
    animation.on_start.add_listener(lambda: script_events.append('start'))
    for name in ('play', 'update', 'step_complete', 'tween_created'):
        getattr(animation, 'on_' + name).add_listener(lambda name=name: script_events.append(name))
    SceneManager.instance().play()
    animation.create_tween()
    animation.do_play()
    tween_api.update(1)
    animation.do_rewind()
    animation.do_kill()
    assert first.count == 0 and second.count == 1111
    assert script_events.count('tween_created') == script_events.count('start') == 1
    assert script_events.count('step_complete') == 1
    assert 'play' in script_events and 'update' in script_events
    assert animation._persistent_events['start'][0].component_identity == second.component_id


def test_persistent_edits_invalidate_bindings_and_blank_entries_do_not_invoke(owner):
    _, obj = owner
    receiver = obj.add_component(EventReceiver)
    animation = obj.add_component(TweenAnimation)
    animation.on_start_entries = [TweenCallback(), callback(receiver, 1)]
    animation._invoke_event('start')
    old = animation._persistent_events['start'][1]
    animation._invoke_event('start')
    assert animation._persistent_events['start'][1] is old and receiver.count == 2
    animation.on_start_entries[1].arguments[0].int_value = 5
    animation.on_validate()
    assert '_persistent_events' not in animation.__dict__
    animation._invoke_event('start')
    assert receiver.count == 7
    animation.on_disable()
    assert '_persistent_events' not in animation.__dict__


def test_persistent_preview_uses_no_runtime_events(owner, monkeypatch):
    from infernux.application import Application
    from infernux.engine.interaction.previews import PreviewService
    monkeypatch.setattr(Application, 'is_headless', staticmethod(lambda: True))
    _, obj = owner
    receiver = obj.add_component(EventReceiver)
    animation = obj.add_component(TweenAnimation)
    for name in animation._event_names:
        setattr(animation, 'on_'+name+'_entries', [callback(receiver, 1)])
    scope = PreviewService().begin('persistent-preview')
    animation.begin_preview(scope)
    animation._preview_manager.manual_update(1, 1)
    scope.close()
    assert receiver.count == 0 and '_persistent_events' not in animation.__dict__


def test_method_picker_excludes_unbindable_signatures_and_refreshes_after_body_reload(monkeypatch):
    from editor.TweenEvents import _methods
    from infernux.engine.runtime_dispatch import publish_runtime_dispatch_epoch
    names = _methods(EventReceiver)
    assert 'Record' in names and 'KeywordOnly' not in names and 'Variadic' not in names
    assert 'VectorArgument' not in names and 'AmbiguousArgument' not in names
    original = EventReceiver.Record
    try:
        monkeypatch.setattr(EventReceiver, 'Record', EventReceiver.KeywordOnly)
        publish_runtime_dispatch_epoch((EventReceiver,)).commit()
        assert 'Record' not in _methods(EventReceiver)
        monkeypatch.setattr(EventReceiver, 'NewMethod', original, raising=False)
        publish_runtime_dispatch_epoch((EventReceiver,)).commit()
        assert 'NewMethod' in _methods(EventReceiver)
    finally:
        monkeypatch.undo()
        publish_runtime_dispatch_epoch((EventReceiver,)).commit()


def test_persistent_callback_membership_is_fixed_for_each_invocation(owner):
    _, obj = owner
    receiver = obj.add_component(EventReceiver)
    receiver.animation = animation = obj.add_component(TweenAnimation)
    animation.on_start_entries = [TweenCallback(target=ComponentRef(receiver), method_name='AddCallback'), callback(receiver, 1)]
    animation._invoke_event('start')
    assert receiver.count == 1 and len(animation.on_start_entries) == 3
    animation._invoke_event('start')
    assert receiver.count == 4 and len(animation.on_start_entries) == 4
    animation.on_start_entries = [TweenCallback(target=ComponentRef(receiver), method_name='RemoveCallback'), callback(receiver, 3)]
    animation._invoke_event('start')
    assert receiver.count == 7 and len(animation.on_start_entries) == 1


def test_destroy_kill_skips_retiring_targets_and_keeps_live_callback_diagnostics(owner, monkeypatch):
    from infernux.components.ref_wrappers import retiring_scene_references
    from infernux.debug import Debug

    scene, obj = owner
    manager = SceneManager.instance()
    surviving_scene = manager.create_scene('Surviving callback scene')
    try:
        retiring = obj.add_component(EventReceiver)
        live = surviving_scene.create_game_object('Live receiver').add_component(EventReceiver)
        animation = obj.add_component(TweenAnimation)
        animation.auto_generate, animation.auto_play, animation.auto_kill = False, False, False
        animation.on_kill_entries = [callback(retiring, 1), callback(live, 10)]
        animation._invoke_event('kill')
        bindings = animation._persistent_events['kill']
        assert retiring.count == 1 and live.count == 10 and bindings[0] is not None

        errors = []
        monkeypatch.setattr(Debug, 'log_error', lambda message, *_args: errors.append(message))
        manager.play()
        animation.create_tween()
        with retiring_scene_references(scene.world_id):
            animation.on_destroy()

        assert retiring.count == 1 and live.count == 20
        assert bindings[0] is None and '_persistent_events' not in animation.__dict__
        assert errors == []
        assert not animation._tween.is_active()
        with pytest.raises(ValueError, match='MissingRecord'):
            invoke_callbacks([TweenCallback(target=ComponentRef(live), method_name='MissingRecord')], [], animation)
    finally:
        manager.unload_scene(surviving_scene)
