"""Public clock queries stay current across configuration and reentrant edits."""
import math

import pytest

from infernux.lib import Vector2, Vector3
import infernux_tween as tween


def scalar(manager, duration):
    return manager.to(lambda: 0., lambda value: None, 1., duration)


def test_manager_defaults_are_captured_at_creation_for_prepared_and_changed_eases():
    manager = tween.TweenManager()
    values = [0., 0., 0.]
    def make(index):
        return manager.to(lambda: 0., lambda value: values.__setitem__(index, value), 1., 1.).set_auto_kill(False)
    prepared = make(0)
    manager.default_ease_type = tween.Ease.OUT_BACK
    manager.default_ease_overshoot_or_amplitude = 2.
    changed = make(1)
    manager.default_ease_type = tween.Ease.LINEAR
    linear = make(2)
    try:
        for handle in (prepared, changed, linear):
            handle.goto(.5)
        assert values == [.75, 1.125, .5]
    finally:
        manager.clear()


def test_total_time_tracks_settings_copy_restart_and_readonly_access():
    manager = tween.TweenManager()
    handle = scalar(manager, 2.)
    try:
        assert handle.full_duration == 2.
        handle.set_loops(3).set_delay(.5)
        assert handle.full_duration == 6.5
        settings = tween.TweenParams().set_loops(2).set_delay(.25).set_auto_kill(False)
        handle.set_as(tween_params=settings)
        assert handle.full_duration == 4.25
        handle.restart(change_delay_to=.75)
        assert handle.full_duration == 4.75
        with pytest.raises(AttributeError):
            handle.full_duration = 10.
    finally:
        manager.clear()


def test_sequence_edits_publish_total_time_before_playback():
    manager = tween.TweenManager()
    child = scalar(manager, 1.).set_loops(2).set_delay(.5)
    root = manager.sequence().set_loops(2).set_delay(.25, False).append(child)
    try:
        assert child.full_duration == 2.
        assert root.full_duration == 5.25
        root.append_interval(.5)
        assert root.full_duration == 6.25
        root.prepend_interval(.25)
        assert root.full_duration == 6.75
        root.insert_callback(4., lambda: None)
        assert root.full_duration == 8.25
    finally:
        manager.clear()


@pytest.mark.parametrize('prepend', [False, True])
def test_adopting_an_infinite_child_converts_its_clock_before_sizing_the_parent(prepend):
    manager = tween.TweenManager()
    child = scalar(manager, .5).set_loops(-1).set_delay(.25)
    assert math.isinf(child.full_duration)
    root = manager.sequence()
    try:
        (root.prepend if prepend else root.append)(child)
        expected_child = 1073741824.
        assert child.full_duration == expected_child
        assert root.full_duration == expected_child and root._entries[0][0] == .25
    finally:
        manager.clear()


@pytest.mark.parametrize('kind', ['scalar', 'circle', 'path'])
def test_reentrant_duration_changes_are_visible_inside_the_setter(kind):
    manager, observed, edited = tween.TweenManager(), [], False
    initial = 0. if kind == 'scalar' else Vector2(1, 0) if kind == 'circle' else Vector3()
    values = [initial]
    def write(value):
        nonlocal edited
        values[0] = value
        if not edited:
            edited = True
            observed.append(handle.full_duration)
            handle.change_end_value(next_end, new_duration=2.)
            observed.append(handle.full_duration)
    if kind == 'scalar':
        handle = manager.to(lambda: values[0], write, 1., 1.)
        next_end = 2.
    elif kind == 'circle':
        handle = manager.to(tween.CirclePlugin.get(), lambda: values[0], write, Vector2(0, 0), 1.)
        handle.set_options(90., False)
        next_end = Vector2(0, 0)
    else:
        end = tween.Path(tween.PathType.LINEAR, [Vector3(1, 0, 0)])
        next_end = tween.Path(tween.PathType.LINEAR, [Vector3(2, 0, 0)])
        handle = manager.to(tween.PathPlugin.get(), lambda: values[0], write, end, 1.)
    try:
        handle.set_ease(tween.Ease.LINEAR).set_loops(2).set_delay(.25).set_auto_kill(False)
        manager.update(.75)
        assert observed == [2.25, 4.25] and handle.full_duration == 4.25
        manager.update(4.)
        assert handle.is_complete()
    finally:
        manager.clear()


def test_recycled_tween_starts_with_its_new_total_time():
    manager = tween.TweenManager()
    previous = scalar(manager, 2.).set_loops(3).set_delay(.5).set_recyclable(True)
    assert previous.full_duration == 6.5
    previous.kill()
    current = scalar(manager, .25)
    try:
        assert current is previous
        assert current.full_duration == .25
        manager.update(.25)
        assert not current.is_active()
    finally:
        manager.clear()
