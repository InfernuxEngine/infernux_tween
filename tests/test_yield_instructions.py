"""Exercise reusable tween waits through the real component coroutine scheduler."""
import pytest

from infernux.coroutine import CoroutineScheduler, WaitUntil
from infernux_tween import (
    TweenManager, TweenYieldInstruction, WaitForCompletion, WaitForElapsedLoops,
    WaitForKill, WaitForPosition, WaitForRewind, WaitForStart,
)


def make_tween():
    manager, value = TweenManager(), [0.0]
    tween = manager.to(lambda: value[0], lambda x: value.__setitem__(0, x), 1.0, 1)
    tween.set_auto_kill(False)
    return manager, tween


@pytest.mark.parametrize("method,args,instruction", [
    ("wait_for_completion", (), WaitForCompletion),
    ("wait_for_kill", (), WaitForKill),
    ("wait_for_start", (), WaitForStart),
    ("wait_for_rewind", (), WaitForRewind),
    ("wait_for_elapsed_loops", (2,), WaitForElapsedLoops),
    ("wait_for_position", (.75,), WaitForPosition),
])
def test_wait_overload_and_kill_release(method, args, instruction):
    manager, tween = make_tween()
    default = getattr(tween, method)(*args)
    wait = getattr(tween, method)(*args, return_custom_yield_instruction=True)
    assert type(default) is WaitUntil
    assert type(wait) is instruction
    assert getattr(TweenYieldInstruction, instruction.__name__) is instruction
    assert wait.keep_waiting and not wait._is_ready()
    tween.kill()
    assert not wait.keep_waiting and wait._is_ready() and default._is_ready()
    manager.clear()


def test_waits_track_delay_loops_completion_and_rewind():
    manager, tween = make_tween()
    tween.set_delay(.5).set_loops(3)
    start, position = WaitForStart(tween), WaitForPosition(tween, 1.5)
    loops, complete, rewind = WaitForElapsedLoops(tween, 2), WaitForCompletion(tween), WaitForRewind(tween)
    manager.update(.25)
    assert start.keep_waiting and position.keep_waiting
    manager.update(.5)
    assert not start.keep_waiting and rewind.keep_waiting
    manager.update(1.25)
    assert not position.keep_waiting and loops.keep_waiting and complete.keep_waiting
    manager.update(.5)
    assert not loops.keep_waiting and complete.keep_waiting
    manager.update(1)
    assert not complete.keep_waiting and WaitForKill(tween).keep_waiting
    tween.rewind()
    assert not rewind.keep_waiting
    assert complete.keep_waiting  # Instructions observe replay rather than latching.
    manager.clear()


def test_custom_waits_resume_real_component_coroutines():
    manager, tween = make_tween()
    scheduler, events = CoroutineScheduler(), []

    def animation():
        yield tween.wait_for_start(True)
        events.append("started")
        yield tween.wait_for_position(.5, True)
        events.append("midpoint")
        yield tween.wait_for_completion(True)
        events.append("complete")
        yield tween.wait_for_kill(True)
        events.append("killed")

    handle = scheduler.start(animation())
    manager.update(.25)
    scheduler.tick_update(.25)
    assert events == ["started"] and not handle.is_finished
    manager.update(.25)
    scheduler.tick_update(.25)
    assert events == ["started", "midpoint"]
    tween.pause()
    manager.update(2)
    scheduler.tick_update(2)
    assert events == ["started", "midpoint"]
    tween.play()
    manager.update(.5)
    scheduler.tick_update(.5)
    assert events[-1] == "complete" and not handle.is_finished
    tween.kill()
    scheduler.tick_update(0)
    assert events[-1] == "killed" and handle.is_finished
    manager.clear()


def test_custom_wait_supports_iterator_and_read_only_waiting_property():
    manager, tween = make_tween()
    wait = WaitForCompletion(tween)
    assert iter(wait) is wait and next(wait) is None and wait.current is None
    assert wait.move_next()
    wait.reset()
    with pytest.raises(AttributeError):
        wait.keep_waiting = False
    manager.update(1)
    assert not wait.move_next()
    with pytest.raises(StopIteration):
        next(wait)
    tween.restart()
    assert next(wait) is None
    manager.clear()
