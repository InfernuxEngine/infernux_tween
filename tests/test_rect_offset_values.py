"""Integer edge storage, typed handles and callback ordering share one route."""
import pytest

from infernux import RectOffset
from infernux_tween import Ease, LoopType, NoOptions, RectOffsetPlugin, TweenManager, TweenerCore

EDGES = ('left', 'right', 'top', 'bottom')

def edges(value):
    return tuple(getattr(value, name) for name in EDGES)


def make(manager, start, end, explicit, ease=Ease.LINEAR):
    values = []
    arguments = (lambda: start, values.append, end, 1.)
    handle = manager.to(RectOffsetPlugin(), *arguments) if explicit else manager.to(*arguments)
    return handle.set_ease(ease).set_auto_kill(False), values


@pytest.mark.parametrize('explicit', [False, True])
def test_offset_handles_expose_live_reference_storage_and_the_selected_plugin(explicit):
    manager = TweenManager()
    try:
        handle, values = make(manager, RectOffset(1, 2, 3, 4), RectOffset(5, 6, 7, 8), explicit)
        assert isinstance(handle, TweenerCore)
        assert isinstance(handle.get_plugin(), RectOffsetPlugin)
        assert isinstance(handle.plug_options, NoOptions)
        handle.force_init()
        handle.start_value.left = 9
        handle.change_value.right = 12
        handle.goto(.5)
        assert edges(values[-1]) == (11, 8, 5, 6)
    finally:
        manager.clear()


@pytest.mark.parametrize('explicit', [False, True])
def test_offset_interpolation_narrows_integer_channels_before_the_final_sum(explicit):
    manager = TweenManager()
    try:
        handle, values = make(manager, RectOffset(16777217, 0, 0, 0), RectOffset(16777219, 0, 0, 0), explicit)
        handle.goto(.5)
        assert values[-1].left == 16777217
    finally:
        manager.clear()


@pytest.mark.parametrize('explicit', [False, True])
def test_offset_change_and_incremental_base_use_signed_integer_wrapping(explicit):
    manager = TweenManager()
    try:
        handle, values = make(manager, RectOffset(2147483646, 0, 0, 0), RectOffset(-2147483646, 0, 0, 0), explicit)
        handle.goto(.5)
        assert values[-1].left == -2147483648
        handle, values = make(manager, RectOffset(0, 0, 0, 0), RectOffset(1500000000, 0, 0, 0), explicit)
        handle.set_loops(3, LoopType.INCREMENTAL).goto(2.)
        assert values[-1].left == 205032704
        handle.goto(2.5)
        assert values[-1].left == -544967296
    finally:
        manager.clear()


@pytest.mark.parametrize('explicit', [False, True])
def test_offset_callback_reads_live_change_but_uses_the_prepared_start(explicit):
    manager = TweenManager()
    armed = False
    try:
        def ease(t, d, a, p):
            if armed:
                handle.start_value.left = 99
                handle.change_value.left = 8
            return t / d
        handle, values = make(manager, RectOffset(1, 0, 0, 0), RectOffset(5, 0, 0, 0), explicit, ease)
        handle.force_init()
        armed = True
        handle.goto(.5)
        assert values[-1].left == 5
        handle.goto(.75)
        assert values[-1].left == 105
    finally:
        manager.clear()


def test_derived_offset_plugin_retains_its_virtual_sampling_callback():
    class Custom(RectOffsetPlugin):
        def evaluate_and_apply(self, *arguments):
            calls.append(arguments[5])
            return super().evaluate_and_apply(*arguments)
    manager, values, calls = TweenManager(), [], []
    try:
        plugin = Custom()
        handle = manager.to(plugin, lambda: RectOffset(), values.append, RectOffset(4, 8, 12, 16), 1.)
        handle.set_ease(Ease.LINEAR).set_auto_kill(False).goto(.5)
        assert handle.get_plugin() is plugin and calls == [.5]
        assert edges(values[-1]) == (2, 4, 6, 8)
    finally:
        manager.clear()


def test_offset_speed_uses_float_channels_and_ieee_division():
    import math
    plugin = RectOffsetPlugin()
    assert plugin.get_speed_based_duration(NoOptions(), 1., RectOffset(0, 16777217, 0, 0)) == 16777216
    assert plugin.get_speed_based_duration(NoOptions(), -2., RectOffset(0, 3, 0, 4)) == -2.5
    assert plugin.get_speed_based_duration(NoOptions(), 0., RectOffset(0, 3, 0, 4)) == math.inf
    assert math.isnan(plugin.get_speed_based_duration(NoOptions(), 0., RectOffset()))


def test_offset_reentrant_sampling_preserves_the_shared_prepared_base_order():
    manager, nested_values = TweenManager(), []
    armed = False
    try:
        nested = manager.to(lambda: RectOffset(10, 0, 0, 0), nested_values.append, RectOffset(18, 0, 0, 0), 1.)
        nested.set_ease(Ease.LINEAR).set_auto_kill(False).force_init()
        def ease(t, d, a, p):
            if armed:
                nested.goto(.5)
            return t / d
        outer, values = make(manager, RectOffset(1, 0, 0, 0), RectOffset(5, 0, 0, 0), False, ease)
        outer.force_init()
        armed = True
        outer.goto(.5)
        assert values[-1].left == 12 and nested_values[-1].left == 14
    finally:
        manager.clear()
