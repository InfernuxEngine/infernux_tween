from infernux.components import ComponentRef, InxComponent, serialized_field
from infernux.components.fields import get_raw_field_value
from infernux.lib import SceneManager
from infernux.ui.ui_event_entry import UIEventArgument
from infernux_tween import DOTween, Ease
from infernux_tween.events import TweenCallback
from runtime.DOTweenAnimation import DOTweenAnimation
from test_links import owner


class EventReceiver(InxComponent):
    count: int = serialized_field(default=0)

    def Record(self, amount: int):
        self.count += amount

    def KeywordOnly(self, *, amount: int):
        self.count += amount

    def Variadic(self, *amounts):
        self.count += sum(amounts)

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
    animation = obj.add_component(DOTweenAnimation)
    animation.auto_play, animation.ease = False, Ease.Linear
    for name, amount in [('start', 1), ('complete', 10), ('rewind', 100), ('kill', 1000)]:
        saved = callback(second, amount)._serialize()
        restored = TweenCallback._deserialize(saved)
        assert get_raw_field_value(restored, 'target').component_id == second.component_id
        setattr(animation, 'on_'+name+'_entries', [restored])
    script_events = []
    animation.on_start.add_listener(lambda: script_events.append('start'))
    SceneManager.instance().play()
    animation.CreateTween().Play()
    DOTween.Update(1)
    animation.DORewind().DOKill()
    assert first.count == 0 and second.count == 1111
    assert script_events == ['start']
    assert animation._persistent_events['start'][0].component_identity == second.component_id


def test_persistent_edits_invalidate_bindings_and_blank_entries_do_not_invoke(owner):
    _, obj = owner
    receiver = obj.add_component(EventReceiver)
    animation = obj.add_component(DOTweenAnimation)
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
    animation = obj.add_component(DOTweenAnimation)
    for name in ('start', 'complete', 'rewind', 'kill'):
        setattr(animation, 'on_'+name+'_entries', [callback(receiver, 1)])
    scope = PreviewService().begin('persistent-preview')
    animation.BeginPreview(scope)
    animation._preview_manager.ManualUpdate(1, 1)
    scope.close()
    assert receiver.count == 0 and '_persistent_events' not in animation.__dict__


def test_method_picker_excludes_unbindable_signatures_and_refreshes_after_body_reload(monkeypatch):
    from editor.TweenEvents import _methods
    from infernux.engine.runtime_dispatch import publish_runtime_dispatch_epoch
    names = _methods(EventReceiver)
    assert 'Record' in names and 'KeywordOnly' not in names and 'Variadic' not in names
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
    receiver.animation = animation = obj.add_component(DOTweenAnimation)
    animation.on_start_entries = [TweenCallback(target=ComponentRef(receiver), method_name='AddCallback'), callback(receiver, 1)]
    animation._invoke_event('start')
    assert receiver.count == 1 and len(animation.on_start_entries) == 3
    animation._invoke_event('start')
    assert receiver.count == 4 and len(animation.on_start_entries) == 4
    animation.on_start_entries = [TweenCallback(target=ComponentRef(receiver), method_name='RemoveCallback'), callback(receiver, 3)]
    animation._invoke_event('start')
    assert receiver.count == 7 and len(animation.on_start_entries) == 1
