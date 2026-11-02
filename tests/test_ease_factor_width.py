"""Ease factors cross a Single boundary while target storage keeps its own type."""
import struct
import numpy as np
import pytest
from infernux_tween import Ease, EaseManager, TweenManager


single = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]


@pytest.mark.parametrize('kind', [float, np.float64, np.float32])
def test_scalar_target_keeps_its_type_and_multiplies_a_single_width_factor(kind):
    manager, values = TweenManager(), []
    try:
        handle = manager.to(lambda: kind(0), values.append, kind(3), 3.).set_ease(Ease.LINEAR)
        handle.goto(1.)
        assert type(values[-1]) is kind
        assert values[-1] == kind(3 * single(1 / 3))
    finally:
        manager.clear()


def test_compiled_ease_returns_single_width_factors_for_scalar_and_list_sampling():
    linear = EaseManager.compile(Ease.LINEAR)
    assert linear(1 / 3) == single(1 / 3)
    assert linear.sample(2 / 3) == single(2 / 3)
    assert linear.sample_many([1 / 3, 2 / 3]) == [single(1 / 3), single(2 / 3)]
    assert EaseManager.compile(Ease.OUT_QUAD).sample(1 / 3) == single(5 / 9)


def test_native_bulk_easing_writes_single_width_factors_into_double_storage():
    progress = np.linspace(.001, .999, 1024, dtype=np.float64)
    expected = progress.astype(np.float32).astype(np.float64)
    output = np.empty_like(progress)
    EaseManager.compile(Ease.LINEAR).sample_into(progress, output)
    assert np.array_equal(output, expected)


@pytest.mark.parametrize('orientation', ['reverse_yoyo', 'inverted'])
def test_linear_sequence_keeps_exact_child_time_without_factor_round_trips(orientation):
    from infernux_tween import LoopType
    manager, values = TweenManager(), []
    try:
        child = manager.to(lambda: np.float32(2), values.append, np.float32(10), 1.)
        child.set_ease(Ease.LINEAR).set_loops(3)
        root = manager.sequence().append(child).set_auto_kill(False)
        if orientation == 'reverse_yoyo':
            root.set_loops(2, LoopType.YOYO)
            root.goto(root.duration())
            root.play_backwards()
            manager.update(.25)
        else:
            root.set_inverted()
            root.goto(2.75)
        assert child.elapsed(False) == .25
        assert values[-1] == np.float32(4.)
    finally:
        manager.clear()
