"""Public playback positions differ from the scheduler's cumulative clock."""
import pytest

from infernux_tween import Ease, LoopType, TweenManager


@pytest.mark.parametrize('mode', list(LoopType))
def test_position_excludes_delay_and_completed_cycles_without_applying_yoyo(mode):
    manager, values = TweenManager(), []
    try:
        handle = manager.to(lambda: 0., values.append, 8., 2.).set_ease(Ease.LINEAR)
        handle.set_delay(.5).set_loops(3, mode).set_auto_kill(False)
        manager.update(.25)
        assert handle.position == 0 and handle.full_position == 0
        manager.update(.5)
        assert handle.position == .25 and handle.full_position == .25
        manager.update(2.)
        assert handle.position == .25 and handle.full_position == 2.25
        handle.goto(2.)
        assert handle.position == 2. and handle.full_position == 2.
        handle.goto(2.25)
        assert handle.position == .25 and handle.elapsed(False) == .25
    finally:
        manager.clear()


@pytest.mark.parametrize('playing', [False, True])
def test_full_position_assignment_seeks_and_preserves_the_playing_state(playing):
    manager, values = TweenManager(), []
    try:
        handle = manager.to(lambda: 0., values.append, 8., 1.).set_ease(Ease.LINEAR)
        handle.set_delay(.5).set_loops(3).set_auto_kill(False)
        if not playing:
            handle.pause()
        handle.full_position = 1.25
        assert handle.full_position == 1.25 and handle.position == .25
        assert handle.is_playing() is playing and values[-1] == 2.
    finally:
        manager.clear()


@pytest.mark.parametrize('field,value', [('position', .5), ('active', False)])
def test_playback_state_properties_are_read_only(field, value):
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda v: None, 1., 1.)
        with pytest.raises(AttributeError):
            setattr(handle, field, value)
        assert handle.active and handle.position == 0 and manager.total_active_tweens() == 1
    finally:
        manager.clear()


def test_sequence_position_and_update_callback_observe_the_same_published_clock():
    manager, observed = TweenManager(), []
    try:
        child = manager.to(lambda: 0., lambda v: None, 1., 1.)
        root = manager.sequence().append(child).set_loops(3).set_auto_kill(False)
        root.on_update(lambda: observed.append((root.position, root.full_position, child.position)))
        root.full_position = 1.25
        assert observed[-1] == (.25, 1.25, .25)
        root.kill()
        assert root.active is False and root.position == 0
    finally:
        manager.clear()


def test_assigning_a_sequenced_child_full_position_does_not_bypass_its_owner():
    manager, values = TweenManager(), []
    try:
        child = manager.to(lambda: 0., values.append, 8., 1.).set_ease(Ease.LINEAR)
        root = manager.sequence().append(child).set_auto_kill(False)
        root.goto(.25)
        child.full_position = .75
        assert root.full_position == .25 and child.full_position == .25 and values[-1] == 2.
    finally:
        manager.clear()
