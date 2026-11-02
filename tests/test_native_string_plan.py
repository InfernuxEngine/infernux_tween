"""String plans own their recipes; large native work releases the GIL once."""
import sys
import threading

from infernux.lib._Infernux import _StringTweenSnapshot
from infernux_tween import Ease, EaseManager, TweenManager


def test_saved_text_plan_keeps_recipe_after_live_options_and_values_change():
    manager, value = TweenManager(), ['']
    try:
        leaf = manager.to(lambda: value[0], lambda v: value.__setitem__(0, v), '<b>AB</b>', 1)
        leaf.set_ease(Ease.LINEAR).set_options(True).force_init()
        saved = leaf._string_plan
        leaf.set_options(False).change_end_value('XYZ', 2)
        assert saved(.5) == '<b>A</b>'
        leaf.goto(1)
        assert value[0] == 'XY'
        assert saved(.5) == '<b>A</b>'
    finally:
        manager.clear()


def test_ordinary_text_keeps_gil_and_large_text_allows_waiting_thread_to_run():
    ease = EaseManager.compile(Ease.LINEAR)
    small = _StringTweenSnapshot('', 'ABCD').bind(ease, 1)
    large = _StringTweenSnapshot('', 'a' * 4_000_000).bind(ease, 1)
    armed, observed = threading.Event(), threading.Event()
    def observe():
        armed.wait()
        observed.set()
    previous = sys.getswitchinterval()
    thread = threading.Thread(target=observe)
    try:
        # Prevent an ordinary interpreter timeslice between arming and checking.
        # Only the large native call should let this waiting Python thread run.
        sys.setswitchinterval(10)
        thread.start()
        armed.set()
        assert small(.5) == 'AB'
        assert not observed.is_set()
        result = large(.5)
        assert observed.is_set()
        assert len(result) == 2_000_000 and result[0] == result[-1] == 'a'
    finally:
        sys.setswitchinterval(previous)
        armed.set()
        thread.join(timeout=5)
