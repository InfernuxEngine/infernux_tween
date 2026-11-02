"""Clock allocation removal must preserve float boundaries and callback ordering."""

from itertools import product
import math
import random
from struct import Struct

from infernux.lib._Infernux import _advance_tween_clock, _tween_float32
from infernux_tween import Ease, TweenManager

FLOAT = Struct("f")
DOUBLE = Struct("d")
BITS = Struct("Q")


def previous_float32(value):
    try:
        return FLOAT.unpack(FLOAT.pack(value))[0]
    except OverflowError:
        # Some CPython builds check native-format float packing, others cast
        # to infinity. The engine uses the same IEEE store on every target.
        return math.copysign(math.inf, value)


def previous_clock(position, delta, scale, backwards, full_duration):
    return min(full_duration, max(0.0, previous_float32(
        position + previous_float32(delta * scale) * (-1 if backwards else 1))))


def assert_same_call(reference, native, *args):
    expected = reference(*args)
    actual = native(*args)
    if math.isnan(expected):
        assert math.isnan(actual), args
    else:
        # Equality alone would miss negative-zero changes at rewind boundaries.
        assert DOUBLE.pack(actual) == DOUBLE.pack(expected), args


def test_float_stores_preserve_rounding_overflow_subnormals_and_signed_zero():
    rng = random.Random(0xC10C)
    boundary = 2.0 ** 128 - 2.0 ** 103
    values = [0.0, -0.0, math.inf, -math.inf, math.nan,
              2.0 ** -149, 2.0 ** -150, -2.0 ** -150,
              boundary, -boundary, math.nextafter(boundary, 0.0),
              math.nextafter(-boundary, 0.0), 1.0 + 2.0 ** -24]
    values.extend(DOUBLE.unpack(BITS.pack(rng.getrandbits(64)))[0] for _ in range(4096))
    for value in values:
        assert_same_call(previous_float32, _tween_float32, value)


def test_clock_fusion_keeps_both_float_stores_and_the_original_clamp_order():
    positions = [-1.0, -0.0, 0.1, 0.999999, 16777215.0, 1e-38, math.inf, math.nan]
    deltas = [0.0, 1.0 / 60, 0.3, 1e-42, 1e38, math.inf, math.nan]
    scales = [0.0, 0.1, 1.0, 3.5, -1.0, 1e30]
    for args in product(positions, deltas, scales, (False, True), (1.0, math.inf, math.nan)):
        assert_same_call(previous_clock, _advance_tween_clock, *args)


def test_startup_getter_changes_the_next_frame_scale_after_the_current_step_is_captured():
    manager = TweenManager()
    values, holder = [0.0], []

    def read():
        holder[0].time_scale = 0.25
        return values[0]

    tween = manager.to(read, lambda v: values.__setitem__(0, v), 1.0, 1.0)
    holder.append(tween)
    try:
        manager.update(0.1)
        assert tween.position == previous_float32(0.1)
        manager.update(.1)
        assert tween.position == .125
    finally:
        manager.clear()


def test_update_callback_changes_the_next_tween_before_its_getter_and_clock():
    manager = TweenManager()
    values, observed = [0.0, 0.0], []
    first = manager.to(lambda: values[0], lambda v: values.__setitem__(0, v), 1.0, 1.0)

    def read_second():
        observed.append(values[0])
        return values[1]

    second = manager.to(read_second, lambda v: values.__setitem__(1, v), 1.0, 1.0)
    first.set_ease(Ease.LINEAR).on_update(lambda: setattr(second, "time_scale", 0.25))
    try:
        manager.update(0.1)
        assert observed == [previous_float32(0.1)]
        assert second.position == previous_float32(0.1 * 0.25)
    finally:
        manager.clear()
