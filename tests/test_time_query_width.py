"""Public time queries retain Single precision with ordinary Python floats."""
import struct
from infernux_tween import Ease, LoopType, TweenManager


single = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]


def test_delayed_time_queries_store_their_single_result():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda value: None, 1., 1.1).set_delay(.1).set_ease(Ease.LINEAR)
        manager.update(.35)
        assert handle.position == .25
        assert handle.elapsed(False) == .25 and handle.elapsed() == .25
        assert handle.full_position == .25
        expected = single(.25 / single(1.1))
        assert handle.elapsed_percentage(False) == expected
        assert handle.elapsed_directional_percentage() == expected
    finally:
        manager.clear()


def test_yoyo_directional_percentage_rounds_the_ratio_before_reversal():
    manager = TweenManager()
    try:
        handle = manager.to(lambda: 0., lambda value: None, 1., 1.1)
        handle.set_loops(3, LoopType.YOYO).set_auto_kill(False).goto(1.35)
        fraction = single(.25 / single(1.1))
        assert handle.position == .25
        assert handle.elapsed_percentage(False) == fraction
        assert handle.elapsed_directional_percentage() == single(1 - fraction)
        assert handle.elapsed() == single(1.35)
    finally:
        manager.clear()
