"""One timeline for playback, seeking and sequences; no engine imports."""

from enum import Enum
from math import floor, inf, isfinite

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
        self._locked = False
        self._backwards = False
        self._callbacks = {}

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
        self._configure()
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

    def _emit(self, name):
        callback = self._callbacks.get(name)
        if callback is not None:
            callback()

    def Play(self):
        if self.active and not self.playing:
            self.playing = True
            if self._owner is not None:
                self._owner._resume(self)
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
        self.Goto(0.0 if include_delay else self.delay)
        return self.Play()

    def Rewind(self, include_delay=True):
        self.Goto(0.0 if include_delay else self.delay)
        return self.Pause()

    def Goto(self, position, and_play=False):
        if not self.active:
            return self
        previous = self.position
        self._seek(min(self.full_duration, max(0.0, float(position))), previous, False)
        if and_play:
            self.Play()
        else:
            self.Pause()
        return self

    def Complete(self, with_callbacks=False):
        if self.loops != -1 and self.active:
            completed = self.IsComplete()
            self._seek(self.full_duration, self.position, bool(with_callbacks))
            if not self.active or self.position != self.full_duration:
                return self
            self.Pause()
            if not with_callbacks and not completed:
                self._emit("complete")
            if self.auto_kill and self.position == self.full_duration:
                self.Kill()
        return self

    def Kill(self, complete=False):
        if not self.active:
            return self
        if complete and self.loops != -1:
            self.Complete()
            if not self.active:
                return self
        self.active = self.playing = False
        if self._owner is not None:
            self._owner._remove(self)
        self._emit("kill")
        self._callbacks.clear()
        return self

    def IsActive(self): return self.active
    def IsPlaying(self): return self.active and self.playing
    def IsComplete(self): return self.position >= self.full_duration
    def Elapsed(self, include_loops=True):
        elapsed = max(0.0, self.position - self.delay)
        if include_loops or self.duration == 0:
            return elapsed
        return self.duration if elapsed and elapsed % self.duration == 0 else elapsed % self.duration

    def _seek(self, position, previous, callbacks):
        self._locked = True
        self.position = position
        if callbacks and not self._started and position >= self.delay:
            self._started = True
            self._emit("start")
            self._emit("play")
            if not self.active:
                return
        elapsed = max(0.0, position - self.delay)
        cycle = floor(elapsed / self.duration) if self.duration else 0
        progress = (elapsed / self.duration - cycle) if self.duration else 1.0
        if elapsed > 0 and progress == 0:
            cycle -= 1
            progress = 1.0
        if self.loop_type == LoopType.Yoyo and cycle % 2:
            progress = 1 - progress
        self._apply(progress, cycle, previous, callbacks)
        if not callbacks or not self.active:
            return
        self._emit("update")
        if self.duration:
            old_cycles = floor(max(0.0, previous - self.delay) / self.duration)
            new_cycles = floor(elapsed / self.duration)
            for _ in range(abs(new_cycles - old_cycles)):
                self._emit("step")
                if not self.active:
                    return
        if previous > 0 and position == 0:
            self._emit("rewind")
        elif position >= self.full_duration and (previous < self.full_duration or self.full_duration == 0):
            self._emit("complete")

    def _advance(self, delta):
        if not self.active or not self.playing:
            return
        previous = self.position
        position = min(self.full_duration, max(0.0, previous + delta * self.timeScale * (-1 if self._backwards else 1)))
        if position < self.delay and previous < self.delay:
            self.position = position
            return
        self._seek(position, previous, True)
        if not self.active or self.position != position:
            return
        if self._backwards and position == 0:
            self.Pause()
        elif not self._backwards and position >= self.full_duration:
            self.Pause()
            if self.auto_kill:
                self.Kill()

    def _apply(self, progress, cycle, previous, callbacks):
        raise NotImplementedError


class Tweener(Tween):
    def __init__(self, getter, setter, end_value, duration):
        super().__init__(duration)
        self._getter, self._setter = getter, setter
        self._end = end_value
        self._start = None
        self._relative = False
        self._from = False
        self._ease = resolve_ease(Ease.OutQuad)

    def SetEase(self, ease):
        self._ease = resolve_ease(ease)
        return self

    def _set_relative(self, relative):
        if not self._from:
            self._relative = relative

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

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        factor = self._ease(progress) + (cycle if self.loop_type == LoopType.Incremental else 0)
        if self._sequence_value:
            value = self._value_type(a + d * factor for a, d in zip(self._start, self._delta))
        else:
            value = self._start + self._delta * factor
        self._setter(value)


class Sequence(Tween):
    def __init__(self):
        super().__init__(0.0)
        self._entries = []
        self._last_insert = 0.0
        self._last_sample = 0.0
        self._sample_cycle = 0
        self._sampled = False
        self._relative = False
        self._ease = resolve_ease(Ease.Linear)

    def SetLoops(self, loops, loop_type=LoopType.Restart):
        if LoopType(loop_type) == LoopType.Incremental:
            raise ValueError("Incremental loops apply to Tweeners, not Sequences")
        return super().SetLoops(loops, loop_type)

    def SetEase(self, ease):
        self._ease = resolve_ease(ease)
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
        if tween._owner is not None:
            tween._owner._remove(tween)
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
        sample = self._ease(progress) * self.duration
        if callbacks and cycle > self._sample_cycle:
            for completed in range(self._sample_cycle, cycle):
                endpoint = 0.0 if self.loop_type == LoopType.Yoyo and completed % 2 else self.duration
                self._sample_children(endpoint, self._last_sample, True, not self._sampled)
                self._sampled = True
                self._last_sample = endpoint
                if self.loop_type != LoopType.Yoyo:
                    self._sample_children(0.0, endpoint, False)
                    self._last_sample = 0.0
                    self._sampled = False
        self._sample_children(sample, self._last_sample, callbacks, not self._sampled)
        self._last_sample = sample
        self._sample_cycle = cycle
        self._sampled = True

    def _sample_children(self, sample, old_sample, callbacks, include_start=False):
        entries = reversed(self._entries) if sample < old_sample else self._entries
        for start, item in entries:
            if not self.active:
                break
            if isinstance(item, Tween):
                if sample >= start or old_sample >= start:
                    item._seek(min(item.full_duration, max(0, sample - start)),
                               min(item.full_duration, max(0, old_sample - start)), callbacks and sample >= start)
            elif callbacks and ((old_sample < start <= sample) or (sample <= start < old_sample)
                                or (include_start and start == 0)):
                item()

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

    def add(self, tween):
        tween._owner = self
        group = self._tweens[tween.update_type]
        group[tween] = None
        if tween.playing:
            self._resume(tween)
        return tween

    def To(self, getter, setter, end_value, duration):
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
        for tween in tuple(self._running[UpdateType(update_type)]):
            tween._advance((unscaled if tween.independent else delta) * self.timeScale)

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

    def Clear(self):
        for group in self._tweens.values():
            for tween in tuple(group):
                tween.Kill()


DOTween = TweenManager()
