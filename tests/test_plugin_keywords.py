"""Direct plugin keywords use the same value and callback path as positional calls."""

import numpy as np
import pytest

from infernux.lib import Vector2, Vector3, quatf
import infernux_tween as api


KINDS = ('float', 'float32', 'uint64', 'color', 'vector', 'string',
         'array', 'euler', 'circle', 'quaternion', 'spiral', 'path')


def make(kind):
    manager = api.TweenManager()
    values = []
    if kind == 'circle':
        handle = manager.to(api.CirclePlugin.get(), lambda: Vector2(0, 1), values.append, Vector2(), 1)
        handle.set_options(90., False)
        start = Vector2(45, 0)
    elif kind == 'quaternion':
        handle = manager.to(api.PureQuaternionPlugin.plug(), quatf.identity, values.append, quatf.euler(0, 90, 0), 1)
        start = quatf.euler(0, 45, 0)
    elif kind == 'spiral':
        handle = manager.to(api.SpiralPlugin.get(), Vector3, values.append, Vector3(0, 0, 1), 1)
        handle.plug_options.frequency = 1.
        handle.plug_options.speed = 1.
        start = Vector3(0, 0, 2)
    elif kind == 'path':
        endpoint = api.Path(api.PathType.LINEAR, [Vector3(1, 0, 0)])
        handle = manager.to(api.PathPlugin.get(), Vector3, values.append, endpoint, 1)
        start = api.Path(api.PathType.LINEAR, [Vector3(2, 0, 0)])
    elif kind == 'array':
        handle = manager.to_array(Vector3, values.append, [Vector3(1, 0, 0), Vector3(2, 0, 0)], [.5, .5])
        start = [Vector3(3, 0, 0), Vector3(4, 0, 0)]
    else:
        initial, endpoint, start = {
            'float': (2., 10., 6.),
            'float32': (np.float32(2), np.float32(10), np.float32(6)),
            'uint64': (np.uint64(2), np.uint64(10), np.uint64(6)),
            'color': ([0., 0., 0., 1.], [1., 1., 1., 1.], [.5, .5, .5, 1.]),
            'vector': (Vector3(2, 3, 4), Vector3(10, 11, 12), Vector3(6, 7, 8)),
            'string': ('ab', 'abcdef', 'cd'),
            'euler': (quatf.identity(), Vector3(0, 90, 0), Vector3(0, 45, 0)),
        }[kind]
        handle = manager.to(lambda: initial, values.append, endpoint, 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    return manager, handle, values, start


def components(value):
    if isinstance(value, str):
        return value
    if np.isscalar(value):
        return float(value)
    return tuple(value)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('explicit', [False, True])
def test_direct_from_accepts_complete_named_overloads(kind, explicit):
    results = []
    for named in (False, True, 'mixed'):
        manager, handle, values, start = make(kind)
        try:
            plugin = handle.get_plugin()
            if named == 'mixed':
                if explicit:
                    plugin.set_from(handle, start, set_immediately=True, is_relative=False)
                else:
                    plugin.set_from(handle, is_relative=False)
            elif named:
                options = dict(t=handle, is_relative=False)
                if explicit:
                    options.update(from_value=start, set_immediately=True)
                plugin.set_from(**options)
            else:
                plugin.set_from(handle, start, True, False) if explicit else plugin.set_from(handle, False)
            if kind not in ('array', 'path', 'spiral'):
                plugin.set_change_value(t=handle)
            handle.goto(.25)
            results.append([components(value) for value in values])
        finally:
            manager.clear()
    assert results[0] == results[1] == results[2]


@pytest.mark.parametrize('kind', KINDS)
def test_direct_apply_accepts_named_owner_without_changing_the_clock(kind):
    results = []
    for named in (False, True):
        manager, handle, values, _ = make(kind)
        try:
            arguments = (handle.plug_options, handle, False, handle.getter, values.append,
                         .25, handle.start_value, handle.change_value, 1., False, 0, api.UpdateNotice.NONE)
            plugin = handle.get_plugin()
            if named:
                names = ('options', 't', 'is_relative', 'getter', 'setter', 'elapsed', 'start_value',
                         'change_value', 'duration', 'using_inverse_position', 'new_completed_steps', 'update_notice')
                plugin.evaluate_and_apply(**dict(zip(names, arguments)))
            else:
                plugin.evaluate_and_apply(*arguments)
            assert handle.elapsed() == 0.
            results.append([components(value) for value in values])
        finally:
            manager.clear()
    assert results[0] == results[1]


def test_path_constructor_accepts_type_keyword_and_retains_path_type_spelling():
    points = [Vector3(), Vector3(1, 0, 0)]
    paths = (api.Path(api.PathType.LINEAR, points),
             api.Path(type=api.PathType.LINEAR, waypoints=points),
             api.Path(path_type=api.PathType.LINEAR, waypoints=points))
    assert all(path.kind == api.PathType.LINEAR and list(path.points) == points for path in paths)
