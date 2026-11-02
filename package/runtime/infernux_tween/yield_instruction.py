"""Reusable tween waits driven by the engine's existing coroutine scheduler."""
from infernux.coroutine import WaitUntil


class _TweenWait(WaitUntil):
    __slots__ = ("tween",)

    def __init__(self, tween):
        self.tween = tween

    def _is_ready(self):
        return not self.keep_waiting

    @property
    def current(self):
        return None

    def move_next(self):
        return self.keep_waiting

    def reset(self):
        pass

    def __iter__(self):
        return self

    def __next__(self):
        if self.keep_waiting:
            return None
        raise StopIteration

    def __repr__(self):
        return f"{type(self).__name__}({self.tween!r})"


class WaitForCompletion(_TweenWait):
    __slots__ = ()

    @property
    def keep_waiting(self):
        return self.tween._active and not self.tween.is_complete()


class WaitForKill(_TweenWait):
    __slots__ = ()

    @property
    def keep_waiting(self):
        return self.tween._active


class WaitForStart(_TweenWait):
    __slots__ = ()

    @property
    def keep_waiting(self):
        return self.tween._active and not self.tween._started


class WaitForRewind(_TweenWait):
    __slots__ = ()

    @property
    def keep_waiting(self):
        tween = self.tween
        return tween._active and (not tween._started or tween._position > tween._delay)


class WaitForElapsedLoops(_TweenWait):
    __slots__ = ("elapsed_loops",)

    def __init__(self, tween, elapsed_loops):
        super().__init__(tween)
        self.elapsed_loops = elapsed_loops

    @property
    def keep_waiting(self):
        return self.tween._active and self.tween.completed_loops() < self.elapsed_loops


class WaitForPosition(_TweenWait):
    __slots__ = ("position",)

    def __init__(self, tween, position):
        super().__init__(tween)
        self.position = position

    @property
    def keep_waiting(self):
        return self.tween._active and self.tween.elapsed() < self.position


class TweenYieldInstruction:
    WaitForCompletion = WaitForCompletion
    WaitForKill = WaitForKill
    WaitForStart = WaitForStart
    WaitForRewind = WaitForRewind
    WaitForElapsedLoops = WaitForElapsedLoops
    WaitForPosition = WaitForPosition
