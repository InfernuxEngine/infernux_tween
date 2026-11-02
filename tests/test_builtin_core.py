"""Live typed-core edits must reach native playback without frame-time polling."""

from copy import copy

import pytest
import numpy as np

from infernux.lib import Vector3
import infernux_tween as api


def make(initial=2., end=10.):
    values = [initial]
    manager = api.TweenManager()
    handle = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), end, 1.)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).pause()
    return manager, handle, values


@pytest.mark.parametrize('initial,end,start,change,expected', [
    (2., 10., 5., 40., 15.),
    (2, 10, 5, 40, 15),
    (Vector3(2, 3, 4), Vector3(10, 12, 14), Vector3(5, 6, 7), Vector3(40, 50, 60), Vector3(15, 18.5, 22)),
])
def test_direct_core_writes_keep_endpoint_independent(initial, end, start, change, expected):
    manager, handle, values = make(initial, end)
    assert isinstance(handle, api.TweenerCore)
    handle.force_init()
    handle.start_value, handle.change_value = start, change
    handle.end_value = end
    job = handle._numeric_job
    handle.goto(.25)
    assert values[0] == expected
    assert handle.end_value == end and handle.change_value == change
    assert handle._numeric_job is job
    handle.goto(.5)
    assert handle._numeric_job is job
    manager.clear()


@pytest.mark.parametrize('initial,end', [(2., 10.), (2, 10)])
def test_startup_discards_direct_start_and_change_but_captures_end_and_getter(initial, end):
    manager, handle, values = make(initial, end)
    handle.start_value, handle.change_value = 90, 300
    assert handle.start_value == 90 and handle.change_value == 300
    handle.end_value = 20 if type(end) is int else 20.
    handle.getter = lambda: 6 if type(end) is int else 6.
    handle.goto(.5)
    assert handle.start_value == 6 and handle.change_value == 14 and values[0] == 13
    replacement = []
    handle.setter = replacement.append
    handle.goto(.25)
    assert replacement == [10 if type(end) is int else 9.5]
    assert values[0] == 13
    manager.clear()


def test_live_options_share_set_options_state_and_copy_on_assignment():
    manager, handle, values = make(Vector3(2, 3, 4), Vector3(10, 12, 14))
    handle.force_init()
    options = handle.plug_options
    assert isinstance(options, api.VectorOptions)
    handle.set_options(api.AxisConstraint.X, True)
    assert options.axis_constraint == api.AxisConstraint.X and options.snapping
    options.axis_constraint = api.AxisConstraint.Y
    options.snapping = False
    values[0] = Vector3(100, 200, 300)
    handle.goto(.25)
    assert values[0] == Vector3(100, 5.25, 300)
    separate = copy(options)
    separate.axis_constraint = api.AxisConstraint.Z
    handle.plug_options = separate
    separate.axis_constraint = api.AxisConstraint.X
    options.axis_constraint = api.AxisConstraint.X
    assert handle.plug_options.axis_constraint == api.AxisConstraint.Z
    handle.goto(.5)
    assert values[0] == Vector3(100, 5.25, 9)
    with pytest.raises(TypeError):
        handle.plug_options = api.ColorOptions()
    manager.clear()


def test_color_plugin_identity_survives_startup_and_old_options_detach_on_recycling():
    manager, color, values = make([0., 0., 0., 0.], [1., 1., 1., 1.])
    plugin = color.get_plugin()
    color.force_init()
    assert color.get_plugin() is plugin
    manager.clear()
    manager = api.TweenManager().init(True)
    first = manager.to(lambda: np.float32(2), lambda v: None, np.float32(10), 1.)
    options = first.plug_options
    options.snapping = True
    first.kill()
    reused = manager.to(lambda: np.float32(2), lambda v: None, np.float32(10), 1.)
    assert reused is first and not options.snapping
    options.snapping = True
    assert not reused.plug_options.snapping
    manager.clear()


def test_color_options_and_scalar_options_are_live():
    manager, scalar, numbers = make(np.float32(2), np.float32(11))
    scalar.force_init()
    assert isinstance(scalar.plug_options, api.FloatOptions)
    scalar.plug_options.snapping = True
    scalar.goto(.25)
    assert numbers[0] == 4
    colors = [[.1, .2, .3, .4]]
    color = manager.to(lambda: colors[0], lambda v: colors.__setitem__(0, v), [.5, .6, .7, .8], 1)
    color.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    color.plug_options.alpha_only = True
    colors[0] = [.8, .7, .6, .4]
    color.goto(.5)
    assert colors[0] == pytest.approx([.8, .7, .6, .6])
    manager.clear()


def test_eager_from_retains_its_direct_start_edit_until_startup():
    manager, handle, values = make()
    handle.from_()
    handle.start_value = 5.
    assert handle.start_value == 5.
    handle.goto(.25)
    assert handle.end_value == 2. and handle.change_value == -3. and values[0] == 4.25
    manager.clear()


@pytest.mark.parametrize('initial,end', [(2., 10.), (2, 10),
    (Vector3(2, 3, 4), Vector3(10, 12, 14)), ([.1, .2, .3, .4], [.5, .6, .7, .8])])
def test_builtin_plugin_can_drive_an_explicit_plugin_tween(initial, end):
    manager, fast, fast_values = make(initial, end)
    fast.set_loops(3, api.LoopType.INCREMENTAL)
    plugin = fast.get_plugin()
    assert isinstance(plugin, api.AbsTweenPlugin) and plugin is fast.get_plugin()
    values = [initial]
    generic = manager.to(plugin, lambda: values[0], lambda v: values.__setitem__(0, v), end, 1)
    generic.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_loops(3, api.LoopType.INCREMENTAL).pause()
    generic.force_init()
    assert generic._numeric_value is not None
    for time in (.25, .75, 1.25, 2.5, 3.):
        generic.goto(time)
        fast.goto(time)
        if isinstance(initial, list):
            assert values[0] == pytest.approx(fast_values[0])
        else:
            assert values[0] == fast_values[0]
    manager.clear()


def test_custom_plugin_handle_uses_the_same_public_core_type():
    manager = api.TweenManager()
    plugin = api.PureQuaternionPlugin.plug()
    from infernux.lib import quatf
    handle = manager.to(plugin, lambda: quatf.identity, lambda v: None, quatf.identity, 1)
    assert isinstance(handle, api.TweenerCore) and handle.get_plugin() is plugin
    manager.clear()
