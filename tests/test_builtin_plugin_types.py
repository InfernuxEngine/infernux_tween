"""Explicit built-in plugin instances retain native playback and their identity."""
import numpy as np
import pytest

from infernux.lib import Vector2, Vector3, vec4f, quatf
from infernux.screen import Rect, RectOffset
import infernux_tween as api


CASES = (
    ('FloatPlugin', np.float32(2), np.float32(10)),
    ('DoublePlugin', np.float64(2), np.float64(10)),
    ('IntPlugin', np.int32(2), np.int32(10)),
    ('LongPlugin', np.int64(2), np.int64(10)),
    ('UintPlugin', np.uint32(2), np.uint32(10)),
    ('UlongPlugin', np.uint64(2), np.uint64(10)),
    ('Vector2Plugin', Vector2(2, 3), Vector2(10, 11)),
    ('Vector3Plugin', Vector3(2, 3, 4), Vector3(10, 11, 12)),
    ('Vector4Plugin', vec4f(2, 3, 4, 5), vec4f(10, 11, 12, 13)),
    ('ColorPlugin', [0., 0., 0., 1.], [1., 1., 1., 1.]),
    ('RectPlugin', Rect(2, 3, 4, 5), Rect(10, 11, 12, 13)),
    ('StringPlugin', 'ab', 'abcdefgh'),
    ('QuaternionPlugin', quatf.identity(), Vector3(0, 90, 0)),
)


def comparable(value):
    return value if isinstance(value, str) or np.isscalar(value) else tuple(value)


@pytest.mark.parametrize('name,initial,endpoint', CASES)
def test_explicit_builtin_uses_the_same_native_sampler_and_keeps_its_instance(name, initial, endpoint):
    plugin = getattr(api, name)()
    assert name in api.__all__ and isinstance(plugin, api.AbsTweenPlugin)
    manager, explicit_values, ordinary_values = api.TweenManager(), [], []
    explicit = manager.to(plugin, lambda: initial, explicit_values.append, endpoint, 1.)
    ordinary = manager.to(lambda: initial, ordinary_values.append, endpoint, 1.)
    try:
        for handle in (explicit, ordinary):
            handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
        assert explicit.get_plugin() is plugin
        assert isinstance(ordinary.get_plugin(), getattr(api, name))
        assert (explicit._string_plan if name == 'StringPlugin' else explicit._numeric_value) is not None
        for time in (.25, .5, 1.):
            explicit.goto(time)
            ordinary.goto(time)
            assert type(explicit_values[-1]) is type(ordinary_values[-1])
            assert comparable(explicit_values[-1]) == comparable(ordinary_values[-1])
    finally:
        manager.clear()


def test_array_factory_returns_its_public_plugin_and_uses_the_prepared_segment_path():
    manager, values = api.TweenManager(), []
    handle = manager.to_array(Vector3, values.append, [Vector3(1, 0, 0), Vector3(2, 0, 0)], [.5, .5])
    try:
        handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
        assert isinstance(handle.get_plugin(), api.Vector3ArrayPlugin) and handle._numeric_segments is not None
        handle.goto(.25)
        assert tuple(values[-1]) == (.5, 0, 0)
        handle.goto(.75)
        assert tuple(values[-1]) == (1.5, 0, 0)
    finally:
        manager.clear()


def test_derived_builtin_plugin_keeps_its_virtual_callback():
    calls, values = [], []
    class EditedFloat(api.FloatPlugin):
        def evaluate_and_apply(self, *args):
            calls.append(args[5])
            super().evaluate_and_apply(*args)
    manager, plugin = api.TweenManager(), EditedFloat()
    handle = manager.to(plugin, lambda: np.float32(0), values.append, np.float32(4), 1.)
    try:
        handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).goto(.5)
        assert handle.get_plugin() is plugin
        assert calls == [.5] and values == [np.float32(2)]
    finally:
        manager.clear()


def test_default_python_scalar_types_and_recycled_plugin_identity_stay_independent():
    manager = api.TweenManager()
    first, second = api.FloatPlugin(), api.FloatPlugin()
    handle = manager.to(first, lambda: np.float32(0), lambda value: None, np.float32(1), 1.).set_recyclable(True)
    handle.kill()
    reused = manager.to(second, lambda: np.float32(0), lambda value: None, np.float32(1), 1.)
    try:
        assert reused is handle and reused.get_plugin() is second
        for initial, endpoint, cls in ((2, 10, api.IntPlugin), (2., 10., api.DoublePlugin)):
            values = []
            ordinary = manager.to(lambda: initial, values.append, endpoint, 1.).set_ease(api.Ease.LINEAR)
            ordinary.goto(.5)
            assert isinstance(ordinary.get_plugin(), cls)
            assert type(values[-1]) is type(initial) and values[-1] == 6
    finally:
        manager.clear()


@pytest.mark.parametrize('mode', ['to', 'from', 'manual'])
@pytest.mark.parametrize('relative', [False, True])
def test_explicit_offset_plugin_preserves_reference_capture_and_incremental_playback(mode, relative):
    results = []
    manager = api.TweenManager()
    try:
        for explicit in (False, True):
            state = [RectOffset(1, 2, 3, 4)]
            endpoint = RectOffset(3, 5, 7, 9)
            arguments = (lambda: state[0], lambda value: state.__setitem__(0, value), endpoint, 1.)
            handle = (manager.to(api.RectOffsetPlugin(), *arguments) if explicit else manager.to(*arguments))
            handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_relative(relative)
            handle.set_loops(3, api.LoopType.INCREMENTAL)
            if mode == 'from':
                handle.from_(relative)
            elif mode == 'manual':
                handle.from_(RectOffset(2, 4, 6, 8), False, relative)
            snapshots = []
            for time in (.25, 1.5, 2.75):
                handle.goto(time)
                snapshots.append(tuple(getattr(state[0], edge) for edge in ('left', 'right', 'top', 'bottom')))
            snapshots.append(tuple(getattr(endpoint, edge) for edge in ('left', 'right', 'top', 'bottom')))
            results.append(snapshots)
        assert results[0] == results[1]
    finally:
        manager.clear()
