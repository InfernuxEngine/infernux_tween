"""Compare fused sampling against the preceding clock, including exact endpoints."""

from itertools import product
from math import floor, inf, nan, nextafter
import random
from struct import pack

from infernux.lib._Infernux import _tween_progress


def previous_progress(position, delay, duration, yoyo, inverted):
    elapsed = max(0.0, position - delay)
    cycle = floor(elapsed / duration) if duration else 0
    progress = (elapsed / duration - cycle) if duration else 1.0
    if elapsed > 0 and progress == 0:
        cycle -= 1
        progress = 1.0
    if yoyo and cycle % 2:
        progress = 1 - progress
    if inverted:
        progress = 1 - progress
    return cycle, progress


def compare(args):
    try:
        expected = previous_progress(*args)
    except (ValueError, OverflowError) as error:
        try:
            _tween_progress(*args)
        except type(error):
            return
        raise AssertionError(("Expected original numeric error", args))
    actual = _tween_progress(*args)
    assert type(actual[0]) is int and actual[0] == expected[0], (args, actual, expected)
    assert pack('d', actual[1]) == pack('d', expected[1]), (args, actual, expected)


def test_sampling_keeps_endpoint_cycles_parity_signed_zero_and_numeric_errors():
    positions = [0., -0., .1, .5, 1., nextafter(1., 0.), nextafter(1., inf),
                 2., 3., -1., 2.**53, 2.**64, 1e300, inf, -inf, nan]
    for args in product(positions, (0., .25, 1., nan),
                        (0., -0., .1, .5, 1., 1e-300, -1., inf, nan),
                        (False, True), (False, True)):
        compare(args)


def test_sampling_keeps_generated_loop_crossings_without_a_tolerance():
    randomizer = random.Random(0xED6E)
    for _ in range(4096):
        duration = 2.**randomizer.randint(-50, 50) * randomizer.uniform(.5, 2.)
        delay = randomizer.uniform(0., 10.)
        loop = randomizer.choice([0, 1, 2, 3, 100, 2**53, 2**64])
        boundary = delay + duration * loop
        position = randomizer.choice([boundary, nextafter(boundary, 0.), nextafter(boundary, inf)])
        compare((position, delay, duration, bool(randomizer.getrandbits(1)),
                 bool(randomizer.getrandbits(1))))
