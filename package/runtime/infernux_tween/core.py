"""Shared playback, seeking and sequence timing."""

from enum import Enum, IntFlag
from math import floor, inf, isfinite, sqrt

from .ease import Ease, resolve_ease


class LoopType(str, Enum):
    Restart = "Restart"
    Yoyo = "Yoyo"
    Incremental = "Incremental"


class UpdateType(str, Enum):
    Normal = "update"
    Late = "late_update"
    Fixed = "fixed_update"
    Manual = "manual"


class AxisConstraint(IntFlag):
    None_ = 0
    X = 1
    Y = 2
    Z = 4
    W = 8


class Tween:
    def __init__(self, duration):
        if not isfinite(duration) or duration < 0:
            raise ValueError("Duration must be finite and nonnegative")
        self.duration = float(duration)
        self.delay = 0.0
        self.loops = 1
        self.loop_type = LoopType.Restart
        self.timeScale = 1.0
        self.auto_kill = True
        self.playing = True
        self.active = True
        self.position = 0.0
        self.target = None
        self.id = None
        self.update_type = UpdateType.Normal
        self.independent = False
        self._parent = None
        self._owner = None
        self._started = False
        self._play_pending = True
        self._locked = False
        self._backwards = False
        self._callbacks = {}
        self._waiters = []
        self._speed_based = False
        self._link = None
        self._seek_serial = 0

    @property
    def full_duration(self):
        return inf if self.loops == -1 else self.delay + self.duration * self.loops

    def _configure(self):
        if self._locked or self._parent is not None:
            raise RuntimeError("Configure a tween before playback or insertion into a sequence")

    def SetDelay(self, delay):
        self._configure()
        if not isfinite(delay) or delay < 0:
            raise ValueError("Delay must be finite and nonnegative")
        self.delay = float(delay)
        return self

    def SetLoops(self, loops, loop_type=LoopType.Restart):
        self._configure()
        if loops < -1 or loops == 0 or (loops == -1 and self.duration == 0):
            raise ValueError("Loops must be positive, or -1 for a nonzero infinite tween")
        self.loops, self.loop_type = int(loops), LoopType(loop_type)
        return self

    def SetAutoKill(self, enabled=True):
        self.auto_kill = bool(enabled)
        return self

    def SetUpdate(self, update_type=UpdateType.Normal, independent=False):
        if self._parent is not None:
            return self
        previous = self.update_type
        self.update_type, self.independent = UpdateType(update_type), bool(independent)
        if self._owner is not None:
            self._owner._move(self, previous)
        return self

    def SetId(self, identity):
        self.id = identity
        return self

    def SetTarget(self, target):
        self.target = target
        return self

    def SetLink(self, target, behaviour=None):
        from .link import LinkBehaviour, TweenLink
        if self._parent is not None:
            raise RuntimeError("Link the root sequence instead of its children")
        if self._link is not None:
            self._link.detach(self)
        link = target.get_component(TweenLink)
        if link is None:
            link = target.add_component(TweenLink)
        link.bind(self, LinkBehaviour.KillOnDestroy if behaviour is None else LinkBehaviour(behaviour))
        return self

    def SetRelative(self, relative=True):
        self._configure()
        self._set_relative(bool(relative))
        return self

    def _on(self, name, callback):
        self._callbacks[name] = callback
        return self

    def OnStart(self, callback): return self._on("start", callback)
    def OnPlay(self, callback): return self._on("play", callback)
    def OnPause(self, callback): return self._on("pause", callback)
    def OnUpdate(self, callback): return self._on("update", callback)
    def OnStepComplete(self, callback): return self._on("step", callback)
    def OnComplete(self, callback): return self._on("complete", callback)
    def OnRewind(self, callback): return self._on("rewind", callback)
    def OnKill(self, callback): return self._on("kill", callback)

    def _emit(self, name, position=None):
        callback = self._callbacks.get(name)
        return True if callback is None else self._invoke(callback, self.position if position is None else position)

    def _invoke(self, callback, position, *, sample=None):
        states, tween = [], self
        while True:
            states.append((tween, tween.position, position, tween.playing, tween._seek_serial, sample))
            tween.position = position
            parent = tween._parent
            if parent is None or parent._sample_context is None:
                break
            start = next(start for start, child in parent._entries if child is tween)
            sample = start + position
            position, tween = parent._callback_sample(sample)[0], parent
        callback()
        interrupted = any(not tween.active or tween.playing != playing or tween.position != clock
                          or tween._seek_serial != serial for tween, _, clock, playing, serial, _ in states)
        for tween, previous, clock, _, serial, sample in states:
            if not interrupted:
                tween.position = previous
            elif isinstance(tween, Sequence) and tween.position == clock and tween._seek_serial == serial:
                if tween._sample_context is None or not tween.duration:
                    tween._sample_cycle, tween._last_progress = tween._progress_at(clock)
                else:
                    tween._sample_cycle = tween._sample_context[0]
                    fraction = (clock - tween.delay) / tween.duration - tween._sample_cycle
                    tween._last_progress = 1 - fraction if tween.loop_type == LoopType.Yoyo and tween._sample_cycle % 2 else fraction
                tween._last_sample = tween._ease(tween._last_progress) * tween.duration if sample is None else sample
                tween._sampled = True
        return not interrupted

    def Play(self):
        if self.active and not self.playing:
            self.playing = True
            self._play_pending = True
            if self._owner is not None:
                self._owner._resume(self)
            if self._started and self.position >= self.delay:
                self._play_pending = False
                self._emit("play")
        return self

    def Pause(self):
        if self.playing:
            self.playing = False
            if self._owner is not None:
                self._owner._pause(self)
            self._emit("pause")
        return self

    def PlayForward(self):
        self._backwards = False
        return self.Play()

    def PlayBackwards(self):
        self._backwards = True
        return self.Play()

    def Restart(self, include_delay=True):
        self._backwards = False
        self._goto(0.0 if include_delay else self.delay)
        return self.Play()

    def Rewind(self, include_delay=True):
        return self._goto(0.0 if include_delay else self.delay)

    def Flip(self):
        self._backwards = not self._backwards
        return self

    def TogglePause(self):
        return self.Pause() if self.playing else self.Play()

    def ForceInit(self):
        self._locked = True
        return self

    def SmoothRewind(self):
        if self.position <= self.delay:
            return self.Rewind(False)
        if self.loop_type != LoopType.Incremental:
            elapsed = self.Elapsed(False)
            cycle = self.CompletedLoops() - int(elapsed == self.duration)
            if self.loop_type == LoopType.Yoyo and cycle % 2:
                elapsed = self.duration - elapsed
            self._goto(self.delay + elapsed)
        return self.PlayBackwards()

    def Goto(self, position, and_play=False):
        return self._goto(self.delay + max(0.0, float(position)), and_play)

    def _goto(self, position, and_play=False):
        if not self.active:
            return self
        self._seek_serial += 1
        serial = self._seek_serial
        self.ForceInit()
        previous = self.position
        self._seek(min(self.full_duration, max(0.0, float(position))), previous, False)
        if self._seek_serial != serial:
            return self
        if and_play:
            self.Play()
        else:
            self.Pause()
        return self

    def Complete(self, with_callbacks=False):
        if self.loops != -1 and self.active:
            self.ForceInit()
            completed = self.IsComplete()
            if self._seek(self.full_duration, self.position, bool(with_callbacks)) is False:
                return self
            if not self.active or self.position != self.full_duration:
                return self
            if not with_callbacks and not completed:
                self._emit("complete")
            if self.active and self.position == self.full_duration:
                self.Kill() if self.auto_kill else self.Pause()
        return self

    def Kill(self, complete=False):
        if not self.active:
            return self
        if complete and self.loops != -1:
            self.Complete()
            if not self.active:
                return self
        self.active = self.playing = False
        if self._link is not None:
            self._link.detach(self)
        if self._owner is not None:
            self._owner._remove(self)
        self._emit("kill")
        self._callbacks.clear()
        self._notify_waiters()
        return self

    def IsActive(self): return self.active
    def IsPlaying(self): return self.active and self.playing
    def IsComplete(self): return self.position >= self.full_duration
    def IsBackwards(self): return self._backwards
    def CompletedLoops(self):
        return floor(max(0.0, self.position - self.delay) / self.duration) if self.duration else int(self.IsComplete())
    def Duration(self, include_loops=True):
        return self.full_duration - self.delay if include_loops else self.duration
    def ElapsedPercentage(self, include_loops=True):
        duration = self.Duration(include_loops)
        return self.Elapsed(include_loops) / duration if 0 < duration < inf else float(self.IsComplete())
    def Elapsed(self, include_loops=True):
        elapsed = max(0.0, self.position - self.delay)
        if include_loops or self.duration == 0:
            return elapsed
        return self.duration if elapsed and elapsed % self.duration == 0 else elapsed % self.duration

    def _progress_at(self, position):
        elapsed = max(0.0, position - self.delay)
        cycle = floor(elapsed / self.duration) if self.duration else 0
        progress = (elapsed / self.duration - cycle) if self.duration else 1.0
        if elapsed > 0 and progress == 0:
            cycle -= 1
            progress = 1.0
        if self.loop_type == LoopType.Yoyo and cycle % 2:
            progress = 1 - progress
        return cycle, progress

    def _seek(self, position, previous, callbacks):
        self._locked = True
        self.position = position
        if callbacks and position >= self.delay:
            if not self._started:
                self._started = True
                if not self._emit("start", self.delay):
                    return False
            if self._play_pending:
                self._play_pending = False
                if not self._emit("play", self.delay):
                    return False
        cycle, progress = self._progress_at(position)
        applied = self._apply(progress, cycle, previous, callbacks)
        self._notify_waiters()
        if applied is False:
            return False
        if not self.active or self.position != position:
            return
        if previous > self.delay and position <= self.delay:
            if not self._emit("rewind"):
                return False
        if not callbacks or not self.active:
            return
        if not self._emit("update"):
            return False
        if self.duration:
            old_cycles = floor(max(0.0, previous - self.delay) / self.duration)
            new_cycles = floor(max(0.0, position - self.delay) / self.duration)
            for _ in range(abs(new_cycles - old_cycles)):
                if not self._emit("step"):
                    return False
                if not self.active:
                    return
        if position >= self.full_duration and (previous < self.full_duration or self.full_duration == 0):
            if not self._emit("complete"):
                return False

    def _advance(self, delta):
        if not self.active or not self.playing:
            return
        previous = self.position
        if not self._locked and previous + delta * self.timeScale >= self.delay:
            self.ForceInit()
        position = min(self.full_duration, max(0.0, previous + delta * self.timeScale * (-1 if self._backwards else 1)))
        if position < self.delay and previous < self.delay:
            self.position = position
            return
        if self._seek(position, previous, True) is False:
            return
        if not self.active or self.position != position:
            return
        if self._backwards and position == 0:
            self.Pause()
        elif not self._backwards and position >= self.full_duration:
            self.Kill() if self.auto_kill else self.Pause()

    def _apply(self, progress, cycle, previous, callbacks):
        raise NotImplementedError

    def _condition(self, kind, value=0):
        check = {
            "complete": self.IsComplete, "kill": lambda: False, "start": lambda: self._started,
            "rewind": lambda: self._started and self.position <= self.delay,
            "loops": lambda: self.CompletedLoops() >= value, "position": lambda: self.Elapsed() >= value,
        }[kind]
        return lambda: not self.active or check()

    def _wait(self, kind, value=0):
        from infernux.coroutine import WaitUntil
        return WaitUntil(self._condition(kind, value))

    async def _async_wait(self, kind, value=0):
        import asyncio
        condition = self._condition(kind, value)
        if condition():
            return
        future = asyncio.get_running_loop().create_future()
        self._waiters.append((condition, future))
        try:
            await future
        finally:
            self._waiters = [(check, waiter) for check, waiter in self._waiters if waiter is not future]

    def _notify_waiters(self):
        for condition, future in tuple(self._waiters):
            if not future.done() and condition():
                future.set_result(None)

    def WaitForCompletion(self): return self._wait("complete")
    def WaitForKill(self): return self._wait("kill")
    def WaitForStart(self): return self._wait("start")
    def WaitForRewind(self): return self._wait("rewind")
    def WaitForElapsedLoops(self, loops): return self._wait("loops", loops)
    def WaitForPosition(self, position): return self._wait("position", position)
    def AsyncWaitForCompletion(self): return self._async_wait("complete")
    def AsyncWaitForKill(self): return self._async_wait("kill")
    def AsyncWaitForStart(self): return self._async_wait("start")
    def AsyncWaitForRewind(self): return self._async_wait("rewind")
    def AsyncWaitForElapsedLoops(self, loops): return self._async_wait("loops", loops)
    def AsyncWaitForPosition(self, position): return self._async_wait("position", position)


class Tweener(Tween):
    def __init__(self, getter, setter, end_value, duration):
        super().__init__(duration)
        self._getter, self._setter = getter, setter
        self._end = end_value
        self._start = None
        self._relative = False
        self._from = False
        self._ease = resolve_ease(Ease.OutQuad)
        self._speed_based = False
        self._constraint = AxisConstraint.None_
        self._snapping = False
        self._alpha_only = False

    def SetEase(self, ease):
        self._ease = resolve_ease(ease)
        return self

    def _set_relative(self, relative):
        if not self._from:
            self._relative = relative

    def SetSpeedBased(self, enabled=True):
        self._configure()
        if enabled and self.duration <= 0:
            raise ValueError("Speed must be positive")
        self._speed_based = bool(enabled)
        return self

    def SetOptions(self, constraint=AxisConstraint.None_, snapping=False, *, alpha_only=False):
        self._configure()
        if isinstance(constraint, bool):
            snapping, constraint = constraint, AxisConstraint.None_
        self._constraint, self._snapping = AxisConstraint(constraint), bool(snapping)
        self._alpha_only = bool(alpha_only)
        return self

    def ForceInit(self):
        self._initialize()
        return super().ForceInit()

    def From(self, relative=False):
        self._configure()
        self._from, self._relative = True, bool(relative)
        self._initialize()
        self._setter(self._start)
        return self

    def _initialize(self):
        if self._start is not None:
            return
        start, end = self._getter(), self._end
        self._integer = type(start) is int
        self._sequence_value = isinstance(start, (tuple, list))
        if self._sequence_value:
            self._value_type = type(start)
            start, end = tuple(start), tuple(end)
            if len(start) != len(end):
                raise ValueError("Tween endpoints must have the same dimensions")
            if self._relative:
                end = tuple(a + b for a, b in zip(start, end))
        elif self._relative:
            end = start + end
        if self._from:
            start, end = end, start
        self._start, self._end = start, end
        self._delta = tuple(b - a for a, b in zip(start, end)) if self._sequence_value else end - start
        if self._speed_based:
            distance = sqrt(sum(float(item)**2 for item in self._delta)) if self._sequence_value or hasattr(self._delta, "__iter__") else abs(self._delta)
            self.duration = distance / self.duration

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        factor = self._ease(progress) + (cycle if self.loop_type == LoopType.Incremental else 0)
        if self._sequence_value:
            value = self._value_type(a + d * factor for a, d in zip(self._start, self._delta))
        else:
            value = self._start + self._delta * factor
        if self._integer:
            value = round(value)
        elif self._constraint or self._alpha_only or self._snapping:
            if isinstance(value, (int, float)):
                value = round(value) if self._snapping else value
            else:
                components = list(value)
                if self._constraint or self._alpha_only:
                    current = self._getter()
                    components = [item if (index == 3 if self._alpha_only else self._constraint & (1 << index))
                                  else current[index] for index, item in enumerate(components)]
                if self._snapping:
                    components = [round(item) for item in components]
                value = self._value_type(components) if self._sequence_value else type(value)(*components)
        self._setter(value)


class Sequence(Tween):
    def __init__(self):
        super().__init__(0.0)
        self._entries = []
        self._last_insert = 0.0
        self._last_sample = 0.0
        self._last_progress = 0.0
        self._sample_cycle = 0
        self._sampled = False
        self._relative = False
        self._ease = resolve_ease(Ease.Linear)
        self._linear_ease = True
        self._sample_context = None

    def SetDelay(self, delay, as_prepended_interval_if_sequence=True):
        return self.PrependInterval(delay) if as_prepended_interval_if_sequence else super().SetDelay(delay)

    def SetLoops(self, loops, loop_type=LoopType.Restart):
        if LoopType(loop_type) == LoopType.Incremental:
            raise ValueError("Incremental loops apply to Tweeners, not Sequences")
        return super().SetLoops(loops, loop_type)

    def SetEase(self, ease):
        self._ease = resolve_ease(ease)
        self._linear_ease = ease == Ease.Linear
        return self

    def _set_relative(self, relative):
        self._relative = relative
        for _, item in self._entries:
            if isinstance(item, Tween):
                item._set_relative(relative)

    def Insert(self, position, tween):
        self._configure()
        if position < 0 or not isfinite(position):
            raise ValueError("Insertion time must be finite and nonnegative")
        if tween is self or tween._parent is not None or tween._started or not tween.active:
            raise ValueError("A sequence owns a live, unstarted tween exactly once")
        if tween.loops == -1:
            raise ValueError("Nested tweens must have finite loops")
        if tween._speed_based:
            raise ValueError("Speed-based tweeners cannot be nested in a sequence")
        if tween._owner is not None:
            tween._owner._remove(tween)
        if tween._link is not None:
            tween._link.detach(tween)
        if self._relative:
            tween._set_relative(True)
        tween._parent = self
        self._entries.append((float(position), tween))
        self._entries.sort(key=lambda entry: entry[0])
        self.duration = max(self.duration, position + tween.full_duration)
        self._last_insert = position
        return self

    def Append(self, tween): return self.Insert(self.duration, tween)
    def Join(self, tween): return self.Insert(self._last_insert, tween)

    def AppendInterval(self, duration):
        self._configure()
        if not isfinite(duration) or duration < 0:
            raise ValueError("Interval must be finite and nonnegative")
        self.duration += duration
        return self

    def PrependInterval(self, duration):
        self.AppendInterval(duration)
        self._entries = [(time + duration, item) for time, item in self._entries]
        self._last_insert += duration
        return self

    def Prepend(self, tween):
        duration = tween.full_duration
        self.PrependInterval(duration)
        return self.Insert(0.0, tween)

    def InsertCallback(self, position, callback):
        self._configure()
        if not isfinite(position) or position < 0:
            raise ValueError("Callback time must be finite and nonnegative")
        self._entries.append((float(position), callback))
        self._entries.sort(key=lambda entry: entry[0])
        self.duration = max(self.duration, position)
        self._last_insert = position
        return self

    def AppendCallback(self, callback): return self.InsertCallback(self.duration, callback)

    def _apply(self, progress, cycle, previous, callbacks):
        if callbacks and cycle > self._sample_cycle:
            for completed in range(self._sample_cycle, cycle):
                endpoint = 0.0 if self.loop_type == LoopType.Yoyo and completed % 2 else 1.0
                if not self._sample_children(endpoint, completed, True):
                    return False
                if self.loop_type != LoopType.Yoyo:
                    self._sample_children(0.0, completed + 1, False)
                    self._sampled = False
        return self._sample_children(progress, cycle, callbacks)

    def _callback_sample(self, sample):
        cycle, start, end = self._sample_context
        if self._linear_ease or not self.duration:
            progress = sample / self.duration if self.duration else start
        else:
            low, high = sorted((start, end))
            increasing = self._ease(low) < self._ease(high)
            for _ in range(32):
                progress = (low + high) / 2
                value = self._ease(progress) * self.duration
                if value == sample:
                    break
                if (value < sample) == increasing:
                    low = progress
                else:
                    high = progress
        fraction = 1 - progress if self.loop_type == LoopType.Yoyo and cycle % 2 else progress
        return self.delay + self.duration * (cycle + fraction), progress

    def _sample_children(self, progress, cycle, callbacks):
        sample, old_sample = self._ease(progress) * self.duration, self._last_sample
        previous_context = self._sample_context
        self._sample_context = (cycle, self._last_progress, progress)
        include_start = not self._sampled
        boundaries = []
        try:
            if callbacks:
                for index, (start, item) in enumerate(self._entries):
                    if isinstance(item, Tween):
                        points = []
                        hooks = item._callbacks
                        if (not item._started and ("start" in hooks or "play" in hooks)) or "rewind" in hooks:
                            points.append(start + item.delay)
                        if "step" in hooks and item.duration:
                            first = max(1, floor((min(sample, old_sample)-start-item.delay)/item.duration))
                            last = min(item.loops, floor((max(sample, old_sample)-start-item.delay)/item.duration))
                            points.extend(start + item.delay + loop*item.duration for loop in range(first, last+1))
                        elif "complete" in hooks:
                            points.append(start + item.full_duration)
                        callback = None
                    else:
                        points, callback = (start,), item
                    for point in set(points):
                        if ((old_sample < point <= sample) or (sample <= point < old_sample)
                                or (include_start and point == 0)):
                            boundaries.append((point, index, callback))
                boundaries.sort(key=lambda entry: entry[:2], reverse=sample < old_sample)
                for point, index, callback in boundaries:
                    clock, boundary = self._callback_sample(point)
                    if not self._sample_items(boundary, cycle, True, index, sample=point):
                        return False
                    if callback is not None and not self._invoke(callback, clock, sample=point):
                        return False
            return self._sample_items(progress, cycle, callbacks)
        finally:
            self._sample_context = previous_context

    def _sample_items(self, progress, cycle, callbacks, before_callback=None, *, sample=None):
        sample = self._ease(progress) * self.duration if sample is None else sample
        old_sample = self._last_sample
        previous_context = self._sample_context
        self._sample_context = (cycle, self._last_progress, progress)
        position, was_playing = self.position, self.playing
        indices = range(len(self._entries)-1, -1, -1) if sample < old_sample else range(len(self._entries))
        try:
            for index in indices:
                start, item = self._entries[index]
                if not self.active or self.position != position or (was_playing and not self.playing):
                    return False
                if isinstance(item, Tween):
                    if before_callback is not None and index > before_callback and start == sample and old_sample <= start:
                        continue
                    if item.active and (sample >= start + item.delay or old_sample >= start + item.delay):
                        if item._seek(min(item.full_duration, max(0, sample - start)),
                                      min(item.full_duration, max(0, old_sample - start)), callbacks and sample >= start) is False:
                            return False
            self._last_sample, self._last_progress = sample, progress
            self._sample_cycle, self._sampled = cycle, True
            return True
        finally:
            self._sample_context = previous_context

    def Kill(self, complete=False):
        super().Kill(complete)
        for _, item in self._entries:
            if isinstance(item, Tween):
                item.Kill()
        return self


class TweenManager:
    def __init__(self, on_activity=None):
        self.timeScale = 1.0
        self._tweens = {phase: {} for phase in UpdateType}
        self._running = {phase: {} for phase in UpdateType}
        self._on_activity = on_activity
        self._update_depth = 0
        self._pending_commits = {}

    def add(self, tween):
        tween._owner = self
        group = self._tweens[tween.update_type]
        group[tween] = None
        if tween.playing:
            self._resume(tween)
        return tween

    def To(self, getter, setter, end_value, duration):
        from infernux.lib import quatf
        if isinstance(end_value, str):
            from .string import StringTweener
            return self.add(StringTweener(getter, setter, end_value, duration))
        if isinstance(end_value, quatf):
            from .rotation import QuaternionTweener
            return self.add(QuaternionTweener(getter, setter, end_value, duration))
        return self.add(Tweener(getter, setter, end_value, duration))

    def Sequence(self):
        return self.add(Sequence())

    def _remove(self, tween):
        group = self._tweens[tween.update_type]
        group.pop(tween, None)
        self._pause(tween)
        tween._owner = None

    def _pause(self, tween):
        running = self._running[tween.update_type]
        if tween in running:
            del running[tween]
            if not running and self._on_activity is not None:
                self._on_activity(tween.update_type, False)

    def _resume(self, tween):
        running = self._running[tween.update_type]
        was_empty = not running
        running[tween] = None
        if was_empty and self._on_activity is not None:
            self._on_activity(tween.update_type, True)

    def _move(self, tween, previous):
        group = self._tweens[previous]
        group.pop(tween)
        running = self._running[previous]
        if tween in running:
            del running[tween]
            if not running and self._on_activity is not None:
                self._on_activity(previous, False)
        self.add(tween)

    def Update(self, delta, unscaled_delta=None, update_type=UpdateType.Normal):
        if not isfinite(delta) or delta < 0:
            raise ValueError("Delta must be finite and nonnegative")
        unscaled = delta if unscaled_delta is None else unscaled_delta
        if not isfinite(unscaled) or unscaled < 0:
            raise ValueError("Unscaled delta must be finite and nonnegative")
        self._update_depth += 1
        try:
            phase = UpdateType(update_type)
            for tween in tuple(self._running[phase]):
                if tween.update_type != phase:
                    continue
                try:
                    tween._advance((unscaled if tween.independent else delta) * self.timeScale)
                except Exception:
                    tween.Kill()
                    raise
        finally:
            self._update_depth -= 1
            if not self._update_depth and self._pending_commits:
                commits, self._pending_commits = self._pending_commits, {}
                for commit in commits:
                    commit()

    def _defer_commit(self, commit):
        if self._update_depth:
            self._pending_commits[commit] = None
        else:
            commit()

    def ManualUpdate(self, delta, unscaled_delta):
        self.Update(delta, unscaled_delta, UpdateType.Manual)

    def _matching(self, target_or_id=None):
        return tuple(tween for group in self._tweens.values() for tween in group
                     if target_or_id is None or tween.target is target_or_id or tween.id == target_or_id)

    def _control(self, action, target_or_id=None, *args):
        matching = self._matching(target_or_id)
        for tween in matching:
            getattr(tween, action)(*args)
        return len(matching)

    def Play(self, target_or_id=None): return self._control("Play", target_or_id)
    def PlayForward(self, target_or_id=None): return self._control("PlayForward", target_or_id)
    def PlayBackwards(self, target_or_id=None): return self._control("PlayBackwards", target_or_id)
    def Pause(self, target_or_id=None): return self._control("Pause", target_or_id)
    def Restart(self, target_or_id=None, include_delay=True): return self._control("Restart", target_or_id, include_delay)
    def Rewind(self, target_or_id=None, include_delay=True): return self._control("Rewind", target_or_id, include_delay)
    def Complete(self, target_or_id=None, with_callbacks=False): return self._control("Complete", target_or_id, with_callbacks)
    def Kill(self, target_or_id=None, complete=False): return self._control("Kill", target_or_id, complete)

    def Goto(self, target_or_id, position, and_play=False):
        return self._control("Goto", target_or_id, position, and_play)

    def IsTweening(self, target_or_id, also_check_if_playing=False):
        return any(not also_check_if_playing or tween.playing for tween in self._matching(target_or_id))

    def TweensById(self, identity, playing_only=False):
        return [tween for tween in self._matching(identity)
                if tween.id == identity and (not playing_only or tween.playing)]

    def TweensByTarget(self, target, playing_only=False):
        return [tween for tween in self._matching(target)
                if tween.target is target and (not playing_only or tween.playing)]

    def TotalActiveTweens(self): return sum(map(len, self._tweens.values()))
    def TotalPlayingTweens(self): return sum(map(len, self._running.values()))

    def GetDiagnostics(self):
        phases = {phase.name: {"active": len(self._tweens[phase]), "playing": len(self._running[phase])}
                  for phase in UpdateType}
        return {"active": sum(item["active"] for item in phases.values()),
                "playing": sum(item["playing"] for item in phases.values()), "phases": phases}

    def Clear(self):
        for group in self._tweens.values():
            for tween in tuple(group):
                tween.Kill()


DOTween = TweenManager()
