"""Stable root order and observable callback boundaries during frame updates."""
import pytest
from infernux_tween import AutoPlay, Ease, LoopType, TweenManager, UpdateType


def tracked(manager, name, events, phase=UpdateType.NORMAL):
    return manager.to(lambda:0.,lambda value:events.append(name),1.,1).set_ease(Ease.LINEAR).set_update(phase)


@pytest.mark.parametrize('paused', [False, True])
def test_transferring_a_tween_releases_the_previous_manager_and_preserves_playback(paused):
    source, destination, values = TweenManager(), TweenManager(), []
    destination.default_auto_play = AutoPlay.NONE
    destination.default_update_type = UpdateType.MANUAL
    destination.default_time_scale_independent = True
    destination.default_ease_type = Ease.IN_CUBIC
    handle = source.to(lambda: 0., values.append, 10., 1.).set_ease(Ease.LINEAR)
    handle.set_recyclable(True).set_auto_kill(False)
    source.update(.25)
    if paused:
        handle.pause()
    destination.add(handle)
    assert source.total_active_tweens() == source.total_playing_tweens() == 0
    assert destination.total_active_tweens() == 1
    assert destination.total_playing_tweens() == int(not paused)
    assert handle.elapsed() == .25 and values == [2.5]
    assert handle.update_type == UpdateType.NORMAL and not handle.independent
    source.update(.25)
    assert handle.elapsed() == .25 and values == [2.5]
    if paused:
        destination.update(.25)
        assert values == [2.5]
        handle.play()
    destination.update(.25)
    assert handle.elapsed() == .5 and values == [2.5, 5.]
    destination.add(handle)
    assert destination.total_active_tweens() == destination.total_playing_tweens() == 1
    handle.kill()
    assert source.total_active_tweens() == destination.total_active_tweens() == 0
    assert source.total_pooled_tweens() == 0 and destination.total_pooled_tweens() == 1
    source.clear(True)
    destination.clear(True)


def test_transferring_a_future_root_during_source_dispatch_prevents_a_second_sample():
    source, destination, events = TweenManager(), TweenManager(), []
    first = tracked(source, 'first', events)
    other = tracked(source, 'other', events)
    first.on_update(lambda: destination.add(other))
    source.update(.25)
    assert events == ['first'] and other.elapsed() == 0
    assert source.total_active_tweens() == destination.total_active_tweens() == 1
    destination.update(.5)
    assert events == ['first', 'other'] and other.elapsed() == .5
    source.clear(True)
    destination.clear(True)


def test_transferring_into_an_active_dispatch_waits_until_its_next_update():
    source, destination, events = TweenManager(), TweenManager(), []
    other = tracked(source, 'moved', events)
    tracked(destination, 'existing', events).on_update(lambda: destination.add(other))
    destination.update(.25)
    assert events == ['existing'] and other.elapsed() == 0
    assert source.total_active_tweens() == 0 and destination.total_active_tweens() == 2
    destination.update(.25)
    assert events == ['existing', 'existing', 'moved'] and other.elapsed() == .25
    source.clear(True)
    destination.clear(True)


def test_resuming_a_tween_preserves_its_creation_order():
    manager, events = TweenManager(), []
    first = manager.to(lambda: 0., lambda value: events.append('first'), 10., 1.)
    manager.to(lambda: 0., lambda value: events.append('second'), 10., 1.)
    manager.update(.25)
    assert events == ['first', 'second']
    first.pause().play()
    events.clear()
    manager.update(.25)
    assert events == ['first', 'second']
    manager.clear()


def test_setter_changes_to_the_update_callback_take_effect_in_the_same_frame():
    manager, events = TweenManager(), []
    def write(value):
        events.append('setter')
        handle.update_callback = lambda: events.append('new')
    handle = manager.to(lambda: 0., write, 10., 1.)
    handle.on_update(lambda: events.append('old'))
    manager.update(.25)
    assert events == ['setter', 'new']
    manager.clear()


def test_sequence_boundary_keeps_each_setter_call_and_updates_child_direction():
    manager, value, writes, steps = TweenManager(), [2.], [], []
    def write(sample):
        value[0] = sample
        writes.append(sample)
    child = manager.to(lambda: value[0], write, 10., 1.).set_ease(Ease.LINEAR)
    child.set_loops(3).on_step_complete(lambda: steps.append('step'))
    manager.sequence().append(child).set_loops(2, LoopType.INCREMENTAL)
    manager.update(2.25)
    writes.clear()
    steps.clear()
    manager.update(.75)
    assert writes == [18., 18.] and steps == ['step']
    assert not child.is_backwards()
    manager.update(.25)
    assert value[0] == 12. and steps == ['step', 'step', 'step']
    assert child.is_backwards()
    manager.clear()


def test_resuming_an_existing_later_tween_executes_it_in_the_current_update():
    manager, events = TweenManager(), []
    first = tracked(manager,'first',events)
    second = tracked(manager,'second',events).pause()
    tracked(manager,'third',events)
    first.on_update(second.play)
    manager.update(.25)
    assert events == ['first','second','third'] and second.elapsed() == .25
    manager.clear()


@pytest.mark.parametrize('during_update',[False,True])
def test_phase_migration_preserves_creation_order(during_update):
    manager, events = TweenManager(), []
    first = tracked(manager,'first',events)
    second = tracked(manager,'second',events,UpdateType.LATE)
    tracked(manager,'third',events)
    tracked(manager,'late',events,UpdateType.LATE)
    if during_update:first.on_update(lambda:second.set_update(UpdateType.NORMAL))
    else:second.set_update(UpdateType.NORMAL)
    manager.update(.25)
    assert events == ['first','second','third']
    manager.update(.125,update_type=UpdateType.LATE)
    assert events == ['first','second','third','late']
    assert manager.total_active_tweens() == 4 and manager.total_playing_tweens() == 4
    manager.clear()


def test_kill_of_a_future_tween_retires_after_the_current_batch_before_pool_reuse():
    manager, events, created = TweenManager(), [], []
    first = tracked(manager,'first',events)
    victim = tracked(manager,'victim',events).set_recyclable(True)
    victim.on_kill(lambda:events.append('retired'))
    tracked(manager,'third',events)
    def replace():
        first.on_update(None)
        victim.kill()
        created.append(tracked(manager,'new',events))
    first.on_update(replace)
    manager.update(.25)
    assert events == ['first','third','retired']
    assert created[0] is not victim and created[0].elapsed() == 0 and manager.total_pooled_tweens() == 1
    events.clear()
    manager.update(.25)
    assert events == ['first','third','new']
    manager.clear()


def test_self_kill_is_retired_at_the_next_visit_to_its_phase():
    manager, events = TweenManager(), []
    first = tracked(manager,'first',events)
    tracked(manager,'late',events,UpdateType.LATE)
    first.on_update(first.kill).on_kill(lambda:events.append('retired'))
    manager.update(.25)
    assert not first.is_active() and not first.is_playing()
    assert events == ['first'] and manager.total_active_tweens() == manager.total_playing_tweens() == 2
    manager.update(.125,update_type=UpdateType.LATE)
    assert events == ['first','late']
    manager.update(.25)
    assert events == ['first','late','retired'] and manager.total_active_tweens() == 1
    manager.clear()


def test_reentrant_update_preserves_both_outer_and_inner_update_callbacks():
    manager, events = TweenManager(), []
    entered = False
    def setter(value):
        nonlocal entered
        events.append('set_first')
        if not entered:
            entered = True
            manager.update(.125)
    first = manager.to(lambda:0.,setter,1.,1).set_ease(Ease.LINEAR).on_update(lambda:events.append('update_first'))
    second = manager.to(lambda:0.,lambda value:events.append('set_second'),1.,1).set_ease(Ease.LINEAR).on_update(lambda:events.append('update_second'))
    manager.update(.25)
    assert events == ['set_first','set_first','update_first','set_second','update_second','update_first','set_second','update_second']
    assert first.elapsed() == second.elapsed() == .375
    manager.clear()


def test_clear_unregisters_a_pending_self_kill_without_replaying_its_deferred_callback():
    manager, events = TweenManager(), []
    handle = tracked(manager,'sample',events).set_recyclable(True)
    handle.on_update(handle.kill).on_kill(lambda:events.append('retired'))
    manager.update(.25)
    assert events == ['sample'] and manager.total_active_tweens() == 1
    manager.clear()
    assert events == ['sample'] and manager.total_active_tweens() == manager.total_pooled_tweens() == 0
    manager.update(.25)
    assert events == ['sample']


@pytest.mark.parametrize('destroy', [False, True])
@pytest.mark.parametrize('pending', [False, True])
def test_global_clear_retains_nested_child_handles_and_root_fields(destroy, pending):
    manager, events = TweenManager(), []
    leaf = tracked(manager, 'leaf', events).on_kill(lambda: events.append('kill_leaf'))
    group = manager.sequence().append(leaf).on_kill(lambda: events.append('kill_group'))
    root = manager.sequence().append(group).set_target(object())
    def updated():
        events.append('root')
        if pending:
            root.kill()
    root.on_update(updated).on_kill(lambda: events.append('kill_root'))
    manager.update(.25)
    manager.clear(destroy)
    assert events == ['leaf', 'root'] + ([] if pending else ['kill_root'])
    assert not root.is_active() and group.is_active() and leaf.is_active()
    assert root.target is not None and root.update_callback is updated
    assert manager.total_active_tweens() == manager.total_pooled_tweens() == 0


def test_reentrant_sequence_seek_reuses_the_already_evaluated_custom_ease_sample():
    manager, calls, value = TweenManager(), [], [0.]
    changed = False
    def write(sample):
        nonlocal changed
        value[0] = sample
        if not changed:
            changed = True
            root.goto(.25, True)
    leaf = manager.to(lambda: value[0], write, 1., 1.).set_ease(Ease.LINEAR)
    def ease(time, duration, amplitude, period):
        calls.append(time)
        return (time / duration) ** 2
    root = manager.sequence().append(leaf).set_ease(ease).set_auto_kill(False)
    root.goto(.75, True)
    assert calls == [.75, .25]
    assert root.elapsed() == .25 and leaf.elapsed() == value[0] == .0625
    manager.clear()
