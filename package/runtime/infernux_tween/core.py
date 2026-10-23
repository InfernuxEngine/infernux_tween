"""Shared playback, seeking and sequence timing."""

from enum import Enum, IntFlag
from math import floor, inf, isfinite, sqrt
from typing import Callable, overload

from infernux.graph.ramp import AnimationCurve

from .ease import Ease, resolve_ease

_UNSET = object()


class LoopType(Enum):
    RESTART = "Restart"
    YOYO = "Yoyo"
    INCREMENTAL = "Incremental"


class UpdateType(Enum):
    NORMAL = "update"
    LATE = "late_update"
    FIXED = "fixed_update"
    MANUAL = "manual"


class AutoPlay(Enum):
    NONE = "None"
    ALL = "All"
    AUTO_PLAY_SEQUENCES = "AutoPlaySequences"
    AUTO_PLAY_TWEENERS = "AutoPlayTweeners"


class AxisConstraint(IntFlag):
    NONE = 0
    X = 1
    Y = 2
    Z = 4
    W = 8


class Tween:
    def __init__(self, duration):
        if not isfinite(duration) or duration < 0:
            raise ValueError("Duration must be finite and nonnegative")
        self._duration = float(duration)
        self._delay = 0.0
        self._loops = 1
        self.loop_type = LoopType.RESTART
        self.time_scale = 1.0
        self.auto_kill = True
        self.playing = True
        self.active = True
        self.position = 0.0
        self.target = None
        self.id = None
        self.update_type = UpdateType.NORMAL
        self.independent = False
        self._parent = None
        self._owner = None
        self._started = False
        self._play_pending = True
        self._locked = False
        self._initialized = False
        self._backwards = False
        self._callbacks = {}
        self._waiters = []
        self._speed_based = False
        self._link = None
        self._seek_serial = 0
        self._inverted = False
        self._relative = False
        self._ease_source = Ease.OUT_QUAD
        self._ease_args = (1.70158, 0.0)
        self._ease_configured = False
        self._update_configured = False
        self._auto_kill_configured = False
        self._loops_configured = False
        self._ease = resolve_ease(self._ease_source, duration=lambda: self._duration)

    @property
    def full_duration(self):
        return inf if self._loops == -1 else self._delay + self._duration * self._loops

    @property
    def _ease_duration(self):
        return self._duration

    @property
    def full_position(self):
        return self.elapsed()

    @full_position.setter
    def full_position(self, value):
        self._goto(self._delay + value, self.playing)

    def _configure(self):
        return self.active and not self._locked and self._parent is None

    @overload
    def set_delay(self, delay: float): ...
    @overload
    def set_delay(self, delay: float, as_prepended_interval_if_sequence: bool): ...
    def set_delay(self, delay: float, as_prepended_interval_if_sequence=_UNSET):
        if not self._configure():
            return self
        if not isfinite(delay) or delay < 0:
            raise ValueError("Delay must be finite and nonnegative")
        self._delay = float(delay)
        return self

    @overload
    def set_loops(self, loops: int): ...
    @overload
    def set_loops(self, loops: int, loop_type: LoopType): ...
    def set_loops(self, loops, loop_type=_UNSET):
        if not self._configure():
            return self
        if type(loops) is not int:
            raise TypeError("loops must be int")
        if loop_type is not _UNSET:
            if not isinstance(loop_type, LoopType):
                raise TypeError("loop_type must be LoopType")
            self.loop_type = loop_type
        self._loops = max(-1, loops) if loops else 1
        self._loops_configured = True
        return self

    def set_auto_kill(self, auto_kill_on_completion: bool=True):
        if self._configure():
            self.auto_kill = auto_kill_on_completion
            self._auto_kill_configured = True
        return self

    @overload
    def set_update(self, is_independent_update: bool): ...
    @overload
    def set_update(self, update_type: UpdateType): ...
    @overload
    def set_update(self, update_type: UpdateType, is_independent_update: bool): ...
    def set_update(self, *args, **kwargs):
        if self._parent is not None:
            return self
        update_type = kwargs.pop("update_type", _UNSET)
        independent = kwargs.pop("is_independent_update", _UNSET)
        if kwargs or len(args) > 2:
            raise TypeError("set_update expects bool, UpdateType, or UpdateType and bool")
        if args:
            if type(args[0]) is bool:
                if len(args) != 1 or independent is not _UNSET:
                    raise TypeError("duplicate independent update argument")
                independent = args[0]
            elif isinstance(args[0], UpdateType):
                if update_type is not _UNSET:
                    raise TypeError("duplicate update type")
                update_type = args[0]
                if len(args) == 2:
                    if independent is not _UNSET:
                        raise TypeError("duplicate independent update argument")
                    independent = args[1]
            else:
                raise TypeError("update_type must be UpdateType")
        if not args and update_type is _UNSET and independent is _UNSET:
            raise TypeError("set_update requires an update type or independent flag")
        defaults = self._owner or _default_manager
        update_type = defaults.default_update_type if update_type is _UNSET else update_type
        independent = defaults.default_time_scale_independent if independent is _UNSET else independent
        if not isinstance(update_type, UpdateType) or type(independent) is not bool:
            raise TypeError("set_update requires UpdateType and bool")
        previous = self.update_type
        self.update_type, self.independent = update_type, independent
        self._update_configured = True
        if self._owner is not None:
            self._owner._move(self, previous)
        return self

    def set_id(self, object_id: object):
        self.id = object_id
        return self

    def set_target(self, target: object):
        self.target = target
        return self

    def set_link(self, game_object, behaviour=_UNSET):
        from .link import LinkBehaviour, TweenLink
        if self._parent is not None:
            raise RuntimeError("Link the root sequence instead of its children")
        if self._link is not None:
            self._link.detach(self)
        link = game_object.get_component(TweenLink)
        if link is None:
            link = game_object.add_component(TweenLink)
        behaviour = LinkBehaviour.KILL_ON_DESTROY if behaviour is _UNSET else behaviour
        if not isinstance(behaviour, LinkBehaviour):
            raise TypeError("behaviour must be LinkBehaviour")
        link.bind(self, behaviour)
        return self

    def set_relative(self, is_relative: bool=True):
        if not self._configure():
            return self
        self._set_relative(is_relative)
        return self

    def _set_relative(self, is_relative):
        self._relative = is_relative

    def set_inverted(self, inverted: bool=True):
        if not self._configure():
            return self
        self._inverted = inverted
        if isinstance(self, Sequence) and self._initialized and not self._sampled:
            self._last_progress = 1.0 if inverted else 0.0
            self._last_sample = self._ease(self._last_progress) * self._duration
        return self

    @overload
    def set_ease(self, ease: Ease): ...
    @overload
    def set_ease(self, ease: Ease, overshoot: float): ...
    @overload
    def set_ease(self, ease: Ease, amplitude: float, period: float): ...
    @overload
    def set_ease(self, custom_ease: Callable[[float, float, float, float], float]): ...
    @overload
    def set_ease(self, anim_curve: AnimationCurve): ...
    def set_ease(self, ease=_UNSET, *args, **kwargs):
        for name in ("anim_curve", "custom_ease"):
            if name in kwargs:
                if ease is not _UNSET:
                    raise TypeError("duplicate ease argument")
                ease = kwargs.pop(name)
        defaults = self._owner or _default_manager
        amplitude, period = defaults.default_ease_overshoot_or_amplitude, defaults.default_ease_period
        if len(args) > 2:
            raise TypeError("set_ease expects ease, optional overshoot, or amplitude and period")
        if args:
            amplitude = args[0]
            if len(args) == 2:
                period = args[1]
        if "overshoot" in kwargs:
            if args or "amplitude" in kwargs or "period" in kwargs:
                raise TypeError("overshoot and amplitude/period are different overloads")
            amplitude = kwargs.pop("overshoot")
        elif "amplitude" in kwargs:
            if args or "period" not in kwargs:
                raise TypeError("amplitude requires period")
            amplitude, period = kwargs.pop("amplitude"), kwargs.pop("period")
        if kwargs or ease is _UNSET or (not isinstance(ease, Ease) and (args or amplitude != (self._owner or _default_manager).default_ease_overshoot_or_amplitude)):
            raise TypeError("invalid set_ease overload")
        self._ease_source, self._ease_args = ease, (amplitude, period)
        self._ease = resolve_ease(ease, amplitude, period, lambda: self._ease_duration)
        self._ease_configured = True
        self._linear_ease = ease == Ease.LINEAR
        return self

    def set_as(self, as_tween):
        if not self._configure():
            return self
        parameters = isinstance(as_tween, TweenParams)
        source = as_tween._settings if parameters else as_tween
        if not isinstance(source, Tween):
            raise TypeError("set_as expects Tween or TweenParams")
        if not parameters:
            self.time_scale, self._backwards = source.time_scale, source._backwards
        self.set_update(source.update_type, source.independent)
        self.id = source.id
        for name in ("start", "play", "rewind", "update", "step", "complete", "kill", "waypoint"):
            self._callbacks[name] = source._callbacks.get(name)
        self.auto_kill, self._loops, self.loop_type = source.auto_kill, source._loops, source.loop_type
        self._auto_kill_configured = self._loops_configured = True
        self._delay, self._speed_based = source._delay, source._speed_based
        self._set_relative(source._relative)
        ease = source._ease_source
        if ease == Ease.UNSET:
            ease = Ease.LINEAR if isinstance(self, Sequence) else (self._owner or _default_manager).default_ease_type
        self._ease_source, self._ease_args = ease, source._ease_args
        self._ease = resolve_ease(ease, *source._ease_args, duration=lambda: self._ease_duration)
        self._linear_ease = ease == Ease.LINEAR
        return self

    def _on(self, name, callback):
        self._callbacks[name] = callback
        return self

    def on_start(self, action: Callable[[], None]): return self._on("start", action)
    def on_play(self, action: Callable[[], None]): return self._on("play", action)
    def on_pause(self, action: Callable[[], None]): return self._on("pause", action)
    def on_update(self, action: Callable[[], None]): return self._on("update", action)
    def on_step_complete(self, action: Callable[[], None]): return self._on("step", action)
    def on_complete(self, action: Callable[[], None]): return self._on("complete", action)
    def on_rewind(self, action: Callable[[], None]): return self._on("rewind", action)
    def on_kill(self, action: Callable[[], None]): return self._on("kill", action)

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
                if tween._sample_context is None or not tween._duration:
                    tween._sample_cycle, tween._last_progress = tween._progress_at(clock)
                else:
                    tween._sample_cycle = tween._sample_context[0]
                    fraction = (clock - tween._delay) / tween._duration - tween._sample_cycle
                    tween._last_progress = 1 - fraction if tween.loop_type == LoopType.YOYO and tween._sample_cycle % 2 else fraction
                    if tween._inverted:
                        tween._last_progress = 1 - tween._last_progress
                tween._last_sample = tween._ease(tween._last_progress) * tween._duration if sample is None else sample
                tween._sampled = True
        return not interrupted

    def play(self):
        if self.active and not self.playing:
            self.playing = True
            self._play_pending = True
            if self._owner is not None:
                self._owner._resume(self)
            if self._started and self.position >= self._delay:
                self._play_pending = False
                self._emit("play")
        return self

    def pause(self):
        if self.playing:
            self.playing = False
            if self._owner is not None:
                self._owner._pause(self)
            self._emit("pause")
        return self

    def play_forward(self):
        self._backwards = False
        return self.play()

    def play_backwards(self):
        self._backwards = True
        return self.play()

    def restart(self, include_delay: bool=True, change_delay_to: float=-1):
        self._backwards = False
        if change_delay_to >= 0:
            self._delay = float(change_delay_to)
        self._goto(0.0 if include_delay else self._delay)
        return self.play()

    def rewind(self, include_delay: bool=True):
        return self._goto(0.0 if include_delay else self._delay)

    def flip(self):
        self._backwards = not self._backwards
        return self

    def toggle_pause(self):
        return self.pause() if self.playing else self.play()

    def force_init(self):
        self._initialized = True
        return self

    def smooth_rewind(self):
        if self.position <= self._delay:
            return self.rewind(False)
        if self.loop_type != LoopType.INCREMENTAL:
            elapsed = self.elapsed(False)
            cycle = self.completed_loops() - int(elapsed == self._duration)
            if self.loop_type == LoopType.YOYO and cycle % 2:
                elapsed = self._duration - elapsed
            self._goto(self._delay + elapsed)
        return self.play_backwards()

    def goto(self, to: float, and_play: bool=False):
        return self._goto(self._delay + max(0.0, float(to)), and_play)

    def goto_with_callbacks(self, to: float, and_play: bool=False):
        if self.active:
            self.force_init()
            self._seek_serial += 1
            if self._seek(min(self.full_duration, self._delay + max(0.0, to)), self.position, True) is not False:
                self.play() if and_play else self.pause()
        return self

    def manual_update(self, delta_time: float, unscaled_delta_time: float):
        self._advance(unscaled_delta_time if self.independent else delta_time)
        return self

    def done(self):
        if self._duration == 0:
            self.manual_update(0, 0)
        return self

    def _goto(self, position, and_play=False):
        if not self.active:
            return self
        self._seek_serial += 1
        serial = self._seek_serial
        self.force_init()
        previous = self.position
        self._seek(min(self.full_duration, max(0.0, float(position))), previous, False)
        if self._seek_serial != serial:
            return self
        if and_play:
            self.play()
        else:
            self.pause()
        return self

    def complete(self, with_callbacks: bool=False):
        if self._loops != -1 and self.active:
            self.force_init()
            completed = self.is_complete()
            if self._seek(self.full_duration, self.position, bool(with_callbacks)) is False:
                return self
            if not self.active or self.position != self.full_duration:
                return self
            if not with_callbacks and not completed:
                self._emit("complete")
            if self.active and self.position == self.full_duration:
                self.kill() if self.auto_kill else self.pause()
        return self

    def kill(self, complete: bool=False):
        if not self.active:
            return self
        if complete and self._loops != -1:
            self.complete()
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

    def is_active(self): return self.active
    def is_playing(self): return self.active and self.playing
    def is_complete(self): return self.active and self.position >= self.full_duration and (self._duration > 0 or self._initialized)
    def is_backwards(self): return self.active and self._backwards
    def delay(self): return self._delay if self.active else 0.0
    def elapsed_delay(self): return min(self.position, self._delay) if self.active else 0.0
    def loops(self): return self._loops if self.active else 0
    def is_time_scale_independent(self): return self.active and self.independent
    def is_initialized(self): return self.active and self._initialized
    def elapsed_directional_percentage(self):
        if not self.active or not self._duration:
            return 0.0
        progress = self._progress_at(self.position)[1]
        return 1-progress if self._inverted else progress
    def is_looping_or_executing_backwards(self):
        return self.active and (self._backwards != (self.loop_type == LoopType.YOYO and self.completed_loops() % 2 == 1))
    def completed_loops(self):
        if not self.active:
            return 0
        return floor(max(0.0, self.position - self._delay) / self._duration) if self._duration else int(self.is_complete())
    def duration(self, include_loops: bool=True):
        if not self.active:
            return 0.0
        return self.full_duration - self._delay if include_loops else self._duration
    def elapsed_percentage(self, include_loops: bool=True):
        duration = self.duration(include_loops)
        return self.elapsed(include_loops) / duration if 0 < duration < inf else 0.0
    def elapsed(self, include_loops: bool=True):
        if not self.active:
            return 0.0
        elapsed = max(0.0, self.position - self._delay)
        if include_loops or self._duration == 0:
            return elapsed
        return self._duration if elapsed and elapsed % self._duration == 0 else elapsed % self._duration

    def _progress_at(self, position):
        elapsed = max(0.0, position - self._delay)
        cycle = floor(elapsed / self._duration) if self._duration else 0
        progress = (elapsed / self._duration - cycle) if self._duration else 1.0
        if elapsed > 0 and progress == 0:
            cycle -= 1
            progress = 1.0
        if self.loop_type == LoopType.YOYO and cycle % 2:
            progress = 1 - progress
        if self._inverted:
            progress = 1 - progress
        return cycle, progress

    def _incremental_cycles(self, cycle):
        offset = cycle if self.loop_type == LoopType.INCREMENTAL else 0
        parent = self._parent
        if parent is not None:
            parent_cycle = parent._sample_context[0] if parent._sample_context else parent._sample_cycle
            offset += parent._incremental_cycles(parent_cycle) * (self._loops if self.loop_type == LoopType.INCREMENTAL else 1)
        return offset

    def _seek(self, position, previous, callbacks):
        if not self._initialized:
            self.force_init()
        self._locked = True
        self.position = position
        if callbacks and position >= self._delay:
            if not self._started:
                self._started = True
                if not self._emit("start", self._delay):
                    return False
            if self._play_pending:
                self._play_pending = False
                if not self._emit("play", self._delay):
                    return False
        cycle, progress = self._progress_at(position)
        applied = self._apply(progress, cycle, previous, callbacks)
        self._notify_waiters()
        if applied is False:
            return False
        if not self.active or self.position != position:
            return
        if previous > self._delay and position <= self._delay:
            if not self._emit("rewind"):
                return False
        if not callbacks or not self.active:
            return
        if not self._emit("update"):
            return False
        if self._duration:
            old_cycles = floor(max(0.0, previous - self._delay) / self._duration)
            new_cycles = floor(max(0.0, position - self._delay) / self._duration)
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
        self._locked = True
        if delta * self.time_scale == 0 and self._duration > 0:
            return
        previous = self.position
        if not self._initialized and previous + delta * self.time_scale >= self._delay:
            self.force_init()
        position = min(self.full_duration, max(0.0, previous + delta * self.time_scale * (-1 if self._backwards else 1)))
        if position < self._delay and previous < self._delay:
            self.position = position
            return
        if self._seek(position, previous, True) is False:
            return
        if not self.active or self.position != position:
            return
        if self._backwards and position == 0:
            self.pause()
        elif not self._backwards and position >= self.full_duration:
            self.kill() if self.auto_kill else self.pause()

    def _apply(self, progress, cycle, previous, callbacks):
        raise NotImplementedError

    def _condition(self, kind, value=0):
        check = {
            "complete": self.is_complete, "kill": lambda: False, "start": lambda: self._started,
            "rewind": lambda: self._started and self.position <= self._delay,
            "loops": lambda: self.completed_loops() >= value, "position": lambda: self.elapsed() >= value,
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

    def wait_for_completion(self): return self._wait("complete")
    def wait_for_kill(self): return self._wait("kill")
    def wait_for_start(self): return self._wait("start")
    def wait_for_rewind(self): return self._wait("rewind")
    def wait_for_elapsed_loops(self, elapsed_loops): return self._wait("loops", elapsed_loops)
    def wait_for_position(self, position): return self._wait("position", position)
    def async_wait_for_completion(self): return self._async_wait("complete")
    def async_wait_for_kill(self): return self._async_wait("kill")
    def async_wait_for_start(self): return self._async_wait("start")
    def async_wait_for_rewind(self): return self._async_wait("rewind")
    def async_wait_for_elapsed_loops(self, elapsed_loops): return self._async_wait("loops", elapsed_loops)
    def async_wait_for_position(self, position): return self._async_wait("position", position)


class Tweener(Tween):
    def __init__(self, getter, setter, end_value, duration):
        super().__init__(duration)
        self._getter, self._setter = getter, setter
        self._end = end_value
        self._start = None
        self._relative = False
        self._from = False
        self._from_value = self._manual_start = _UNSET
        self._speed_based = False
        self._constraint = AxisConstraint.NONE
        self._snapping = False
        self._alpha_only = False
        self._euler = False
        self._use_shortest360_route = True
        self._vector_option = _UNSET
        self._vector_option_kind = None
        self._rotate_mode = None
        self._sample_rotation = None
        self._no_from = False

    def _set_relative(self, relative):
        if not self._from:
            self._relative = relative

    def set_speed_based(self, is_speed_based: bool=True):
        if not self._configure():
            return self
        if is_speed_based and self._duration <= 0:
            raise ValueError("Speed must be positive")
        self._speed_based = is_speed_based
        return self

    def force_init(self):
        if not self._initialized:
            self._initialize()
            if self._speed_based:
                self._duration = self._distance() / self._duration
        return super().force_init()

    @overload
    def from_(self): ...
    @overload
    def from_(self, is_relative: bool): ...
    @overload
    def from_(self, set_immediately: bool, is_relative: bool): ...
    @overload
    def from_(self, from_value: object, set_immediately: bool=True, is_relative: bool=False): ...
    def from_(self, *args, **kwargs):
        if not self._configure():
            return self
        from_value = kwargs.pop("from_value", _UNSET)
        immediate = kwargs.pop("set_immediately", _UNSET)
        relative = kwargs.pop("is_relative", _UNSET)
        if kwargs or len(args) > 3:
            raise TypeError("invalid from_ overload")
        if args and type(args[0]) is bool:
            if from_value is not _UNSET or immediate is not _UNSET or len(args) > 2:
                raise TypeError("bool From uses relative or set_immediately/is_relative")
            if len(args) == 2:
                if relative is not _UNSET:
                    raise TypeError("duplicate is_relative")
                immediate, relative = args
            elif relative is not _UNSET:
                immediate = args[0]
            else:
                relative = args[0]
        elif args:
            if from_value is not _UNSET:
                raise TypeError("duplicate from_value")
            from_value = args[0]
            if len(args) >= 2:
                if immediate is not _UNSET:
                    raise TypeError("duplicate set_immediately")
                immediate = args[1]
            if len(args) == 3:
                if relative is not _UNSET:
                    raise TypeError("duplicate is_relative")
                relative = args[2]
        elif from_value is _UNSET and immediate is not _UNSET and relative is _UNSET:
            raise TypeError("the two-bool From overload requires is_relative")
        set_immediately = True if immediate is _UNSET else immediate
        relative = False if relative is _UNSET else relative
        if type(set_immediately) is not bool or type(relative) is not bool:
            raise TypeError("set_immediately and is_relative must be bool")
        if self._no_from:
            return self
        self._from, self._relative = True, relative
        self._from_value = from_value
        self._start = None
        if set_immediately or from_value is not _UNSET:
            self._initialize()
        if set_immediately:
            if self._euler:
                from infernux.lib import quatf
                self._setter(quatf.euler(*self._start))
            else:
                self._setter(self._snap(self._start) if self._snapping else self._start)
        return self

    def _relative_value(self, current, value):
        if self._alpha_only:
            return type(current)((*current[:3], current[3] + value[3]))
        return type(current)(a+b for a, b in zip(current, value, strict=True)) if isinstance(current, (tuple, list)) else current+value

    def _capture_values(self):
        current, end = self._getter(), self._end
        from infernux.lib import Vector3, quatf
        if isinstance(current, quatf) and isinstance(end, Vector3):
            from .rotation import RotateMode, _sample_euler
            self._euler, self._rotation_start = True, current
            self._sample_rotation = _sample_euler
            current = current.euler_angles
            if self._vector_option_kind in ('axis', 'snapping'):
                raise TypeError("quaternion Euler options accept use_shortest360_route")
            if self._vector_option is not _UNSET:
                self._use_shortest360_route, self._snapping = self._vector_option, False
            if self._rotate_mode is None:
                self._rotate_mode = RotateMode.FAST if self._use_shortest360_route else RotateMode.FAST_BEYOND360
        elif self._vector_option_kind == 'euler':
            raise TypeError("use_shortest360_route requires a quaternion getter")
        self._integer = type(current) is int
        self._sequence_value = isinstance(current, (tuple, list))
        self._value_type = type(current)
        start = current if self._manual_start is _UNSET else self._manual_start
        if self._from:
            if type(self._from_value) in (int, float):
                if isinstance(current, Vector3):
                    self._from_value = Vector3(self._from_value, self._from_value, self._from_value)
                elif isinstance(current, list) and len(current) == 4:
                    self._alpha_only = True
                    self._from_value = [*current[:3], self._from_value]
            if self._from_value is _UNSET:
                start, end = end, start
            else:
                start = self._from_value
            if self._relative:
                start = self._relative_value(current, start)
                if self._from_value is not _UNSET:
                    end = self._relative_value(current, end)
            if self._constraint or self._alpha_only:
                channels = [value if (i == 3 if self._alpha_only else self._constraint & (1 << i)) else current[i]
                            for i, value in enumerate(start)]
                start = self._value_type(channels) if self._sequence_value else self._value_type(*channels)
        return start, end

    def _set_values(self, start, end):
        if self._euler:
            from infernux.lib import quatf
            if isinstance(start, quatf):
                start = start.euler_angles
        if self._sequence_value:
            start, end = tuple(start), tuple(end)
            if len(start) != len(end):
                raise ValueError("Tween endpoints must have the same dimensions")
        self._start, self._end = start, end
        self._delta = tuple(b - a for a, b in zip(start, end)) if self._sequence_value else end - start
        if self._euler:
            from .rotation import RotateMode
            mode = self._rotate_mode
            if mode == RotateMode.FAST and not self._relative:
                self._delta = type(end)(*(180 if value > 0 and (value + 180) % 360 == 0 else
                                          (value + 180) % 360 - 180 for value in self._delta))

    def _initialize(self):
        if self._start is None:
            start, end = self._capture_values()
            if self._relative and not self._from:
                end = self._relative_value(start, end)
            self._set_values(start, end)

    def _distance(self):
        if self._alpha_only:
            return abs(self._delta[3])
        if self._constraint:
            return sqrt(sum(float(value)**2 for index, value in enumerate(self._delta) if self._constraint & (1 << index)))
        return sqrt(sum(float(item)**2 for item in self._delta)) if self._sequence_value or hasattr(self._delta, "__iter__") else abs(self._delta)

    def change_start_value(self, new_start_value: object, new_duration: float=-1):
        return self._change_values(start=new_start_value, duration=new_duration)

    @overload
    def change_end_value(self, new_end_value: object, new_duration: float=-1, snap_start_value: bool=False): ...
    @overload
    def change_end_value(self, new_end_value: object, snap_start_value: bool): ...
    def change_end_value(self, new_end_value, *args, **kwargs):
        if len(args) == 1 and type(args[0]) is bool and not kwargs:
            new_duration, snap_start_value = -1, args[0]
        else:
            new_duration, snap_start_value = _bind_arguments(('new_duration', 'snap_start_value'), args, kwargs,
                                                            {'new_duration': -1, 'snap_start_value': False})
            if type(new_duration) is bool:
                raise TypeError("new_duration must be a number")
        return self._change_values(end=new_end_value, duration=new_duration, snap_start=snap_start_value)

    def change_values(self, new_start_value: object, new_end_value: object, new_duration: float=-1):
        return self._change_values(start=new_start_value, end=new_end_value, duration=new_duration)

    def _change_values(self, *, start=_UNSET, end=_UNSET, duration=-1, snap_start=False):
        if not self.active or self._parent is not None:
            return self
        if end is not _UNSET:
            self._relative = False
            if start is not _UNSET:
                self._from = False
        if self._start is None:
            self._manual_start = start
            if end is not _UNSET:
                self._end = end
        else:
            first = self._getter() if snap_start and self._initialized else self._start
            self._set_values(first if start is _UNSET else start, self._end if end is _UNSET else end)
        if duration > 0:
            self._duration = self._distance()/duration if self._speed_based and self._initialized else float(duration)
        self.force_init()
        self._seek_serial += 1
        if self._seek(min(self.position, self._delay), self.position, False) is False:
            return self
        if self._backwards:
            self.pause()
        return self

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        factor = self._ease(progress) + self._incremental_cycles(cycle)
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
                value = self._value_type(components) if self._sequence_value else type(value)(*components)
                if self._snapping:
                    value = self._snap(value)
        if self._euler:
            value = self._sample_rotation(self, value, factor)
        self._setter(value)

    def _snap(self, value):
        if isinstance(value, (int, float)):
            return round(value)
        values = [round(item) if not self._constraint or self._constraint & (1 << i) else item
                  for i, item in enumerate(value)]
        return self._value_type(values) if self._sequence_value else self._value_type(*values)


class _FloatTweener(Tweener):
    def set_options(self, snapping: bool):
        if not self._configure():
            return self
        if type(snapping) is not bool:
            raise TypeError("snapping must be bool")
        self._snapping = snapping
        return self


class _ColorTweener(Tweener):
    @overload
    def from_(self, from_alpha_value: float, set_immediately: bool=True, is_relative: bool=False): ...
    @overload
    def from_(self, from_value: list[float], set_immediately: bool=True, is_relative: bool=False): ...
    @overload
    def from_(self, is_relative: bool=False): ...
    @overload
    def from_(self, set_immediately: bool, is_relative: bool): ...
    def from_(self, *args, **kwargs):
        if 'from_alpha_value' in kwargs:
            if args or 'from_value' in kwargs:
                raise TypeError("duplicate From value")
            kwargs['from_value'] = kwargs.pop('from_alpha_value')
        return super().from_(*args, **kwargs)

    def set_options(self, alpha_only: bool):
        if not self._configure():
            return self
        if type(alpha_only) is not bool:
            raise TypeError("alpha_only must be bool")
        self._alpha_only = alpha_only
        return self


class _VectorTweener(Tweener):
    @overload
    def set_options(self, snapping: bool): ...
    @overload
    def set_options(self, axis_constraint: AxisConstraint, snapping: bool=False): ...
    @overload
    def set_options(self, use_shortest360_route: bool=True): ...
    def set_options(self, *args, **kwargs):
        if not self._configure():
            return self
        if 'use_shortest360_route' in kwargs or not args and not kwargs:
            if args or len(kwargs) > 1:
                raise TypeError("invalid quaternion options overload")
            option = kwargs.get('use_shortest360_route', True)
            if type(option) is not bool:
                raise TypeError("use_shortest360_route must be bool")
            self._vector_option, self._vector_option_kind = option, 'euler'
            if self._start is not None:
                if not self._euler:
                    raise TypeError("use_shortest360_route requires a quaternion getter")
                self._use_shortest360_route, self._snapping = option, False
                from .rotation import RotateMode
                self._rotate_mode = RotateMode.FAST if option else RotateMode.FAST_BEYOND360
                self._set_values(self._start, self._end)
            return self
        constraint = kwargs.pop("axis_constraint", _UNSET)
        snapping = kwargs.pop("snapping", _UNSET)
        self._vector_option_kind = 'axis' if constraint is not _UNSET else 'snapping'
        if kwargs or len(args) > 2:
            raise TypeError("invalid vector set_options overload")
        if args:
            if type(args[0]) is bool and len(args) == 1 and constraint is _UNSET:
                if snapping is not _UNSET:
                    raise TypeError("duplicate snapping")
                snapping = self._vector_option = args[0]
                self._vector_option_kind = 'bool'
            elif isinstance(args[0], AxisConstraint):
                if constraint is not _UNSET:
                    raise TypeError("duplicate axis_constraint")
                constraint = args[0]
                self._vector_option_kind = 'axis'
                if len(args) == 2:
                    if snapping is not _UNSET:
                        raise TypeError("duplicate snapping")
                    snapping = args[1]
            else:
                raise TypeError("vector options need bool or AxisConstraint")
        if constraint is _UNSET and snapping is _UNSET:
            raise TypeError("set_options requires snapping or axis_constraint")
        self._constraint = AxisConstraint.NONE if constraint is _UNSET else constraint
        self._snapping = False if snapping is _UNSET else snapping
        if not isinstance(self._constraint, AxisConstraint) or type(self._snapping) is not bool:
            raise TypeError("vector options need AxisConstraint and bool")
        if self._euler and self._vector_option is not _UNSET:
            self._use_shortest360_route, self._snapping = self._vector_option, False
            from .rotation import RotateMode
            self._rotate_mode = RotateMode.FAST if self._vector_option else RotateMode.FAST_BEYOND360
            self._set_values(self._start, self._end)
        return self


class _ArrayTweener(_VectorTweener):
    def __init__(self, getter, setter, end_values, durations):
        if not end_values or len(end_values) != len(durations) or any(d < 0 or not isfinite(d) for d in durations):
            raise ValueError("end_values and durations must have the same nonzero length")
        super().__init__(getter, setter, end_values[-1], sum(durations))
        self._end_values, self._durations = tuple(end_values), tuple(durations)
        self._segment_duration = self._duration
        self._no_from = True
        self._manual_segments = None

    @property
    def _ease_duration(self):
        return self._segment_duration

    def force_init(self):
        self._initialize()
        if self._speed_based and not self._initialized:
            if any(speed <= 0 for speed in self._durations):
                raise ValueError("segment speeds must be positive")
            self._durations = tuple(sqrt(sum(float(b-a)**2 for a,b in zip(start,end)))/speed
                                    for start,end,speed in zip(self._segment_starts,self._segment_ends,self._durations))
            self._duration = sum(self._durations)
        return Tween.force_init(self)

    def _set_values(self, start, end):
        super()._set_values(start, end)
        starts, ends = [], []
        for index, value in enumerate(self._end_values):
            first = (self._manual_segments[index] if self._manual_segments is not None
                     else start if index == 0 else ends[-1])
            if self._relative and not self._initialized:
                first = start if index == 0 else ends[-1]
                value = self._relative_value(first, value)
            starts.append(first)
            ends.append(value)
        self._segment_starts, self._segment_ends = tuple(starts), tuple(ends)
        self._end_values = self._segment_ends
        self._start, self._end = starts[0], ends[-1]
        self._delta = self._end - self._start

    def _change_values(self, *, start=_UNSET, end=_UNSET, duration=-1, snap_start=False):
        if not self.active or self._parent is not None:
            return self
        if start is not _UNSET:
            if len(start) != len(self._durations):
                raise ValueError("array starts must match the segment count")
            self._manual_segments, start = tuple(start), start[0]
        if end is not _UNSET:
            if len(end) != len(self._durations):
                raise ValueError("array ends must match the segment count")
            self._end_values = tuple(end)
            end = end[-1]
        if snap_start:
            self._manual_segments = None
        return super()._change_values(start=start, end=end, duration=duration, snap_start=snap_start)

    def _distance(self):
        return sum(sqrt(sum(float(b-a)**2 for a,b in zip(start,end))) for start, end in zip(self._segment_starts, self._segment_ends))

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        if self._duration == 0:
            self._setter(self._end)
            return
        clock = progress * self._duration
        duration_scale = self._duration / sum(self._durations) if self._duration else 0
        offset = 0.0
        for index, duration in enumerate(self._durations):
            width = duration * duration_scale
            if clock <= offset + width or index == len(self._durations)-1:
                self._segment_duration = width
                fraction = self._ease((clock-offset)/width) if width else 1.0
                value = self._segment_starts[index] + (self._segment_ends[index]-self._segment_starts[index]) * fraction
                break
            offset += width
        value += self._delta * self._incremental_cycles(cycle)
        if self._constraint or self._snapping:
            current = self._getter()
            value = type(value)(*(round(v) if self._snapping else v for v in
                                 (v if not self._constraint or self._constraint & (1 << i) else current[i]
                                  for i, v in enumerate(value))))
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
        self._ease_source = Ease.LINEAR
        self._ease = resolve_ease(Ease.LINEAR, duration=lambda: self._duration)
        self._linear_ease = True
        self._sample_context = None

    def set_delay(self, delay, as_prepended_interval_if_sequence=True):
        return self.prepend_interval(delay) if as_prepended_interval_if_sequence else super().set_delay(delay)

    def force_init(self):
        if not self._initialized and self._inverted:
            self._last_progress = 1.0
            self._last_sample = self._ease(1.0) * self._duration
        return super().force_init()

    def set_speed_based(self, is_speed_based=True):
        return self

    def _set_relative(self, relative):
        self._relative = relative
        for _, item in self._entries:
            if isinstance(item, Tween):
                item._set_relative(relative)

    def insert(self, at_position, t):
        if not self._configure():
            return self
        if at_position < 0 or not isfinite(at_position):
            raise ValueError("Insertion time must be finite and nonnegative")
        if t is self or t._parent is not None or t._started or not t.active:
            raise ValueError("A sequence owns a live, unstarted tween exactly once")
        if t._loops == -1:
            t._loops = 1
        t._speed_based = False
        if t._owner is not None:
            t._owner._remove(t)
        if t._link is not None:
            t._link.detach(t)
        if self._relative:
            t._set_relative(True)
        t._parent = self
        self._entries.append((float(at_position), t))
        self._entries.sort(key=lambda entry: entry[0])
        self._duration = max(self._duration, at_position + t.full_duration)
        self._last_insert = at_position
        return self

    def append(self, t): return self.insert(self._duration, t)
    def join(self, t): return self.insert(self._last_insert, t)

    def append_interval(self, interval):
        if not self._configure():
            return self
        if not isfinite(interval) or interval < 0:
            raise ValueError("Interval must be finite and nonnegative")
        self._last_insert = self._duration
        self._duration += interval
        return self

    def prepend_interval(self, interval):
        if not self._configure():
            return self
        if not isfinite(interval) or interval < 0:
            raise ValueError("Interval must be finite and nonnegative")
        self._duration += interval
        self._entries = [(time + interval, item) for time, item in self._entries]
        self._last_insert += interval
        return self

    def prepend(self, t):
        duration = t.full_duration
        self.prepend_interval(duration)
        return self.insert(0.0, t)

    def insert_callback(self, at_position, callback):
        if not self._configure():
            return self
        if not isfinite(at_position) or at_position < 0:
            raise ValueError("Callback time must be finite and nonnegative")
        self._entries.append((float(at_position), callback))
        self._entries.sort(key=lambda entry: entry[0])
        self._duration = max(self._duration, at_position)
        self._last_insert = at_position
        return self

    def append_callback(self, callback): return self.insert_callback(self._duration, callback)
    def prepend_callback(self, callback): return self.insert_callback(0.0, callback)
    def join_callback(self, callback): return self.insert_callback(self._last_insert, callback)

    def _apply(self, progress, cycle, previous, callbacks):
        if callbacks and cycle > self._sample_cycle:
            for completed in range(self._sample_cycle, cycle):
                endpoint = 0.0 if self.loop_type == LoopType.YOYO and completed % 2 else 1.0
                if self._inverted:
                    endpoint = 1-endpoint
                if not self._sample_children(endpoint, completed, True):
                    return False
                if self.loop_type != LoopType.YOYO:
                    self._sample_children(1.0 if self._inverted else 0.0, completed + 1, False)
                    self._sampled = False
        return self._sample_children(progress, cycle, callbacks)

    def _callback_sample(self, sample):
        cycle, start, end = self._sample_context
        if self._linear_ease or not self._duration:
            progress = sample / self._duration if self._duration else start
        else:
            low, high = sorted((start, end))
            increasing = self._ease(low) < self._ease(high)
            for _ in range(32):
                progress = (low + high) / 2
                value = self._ease(progress) * self._duration
                if value == sample:
                    break
                if (value < sample) == increasing:
                    low = progress
                else:
                    high = progress
        fraction = 1 - progress if self.loop_type == LoopType.YOYO and cycle % 2 else progress
        if self._inverted:
            fraction = 1-fraction
        return self._delay + self._duration * (cycle + fraction), progress

    def _sample_children(self, progress, cycle, callbacks):
        sample, old_sample = self._ease(progress) * self._duration, self._last_sample
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
                            points.append(start + item._delay)
                        if "step" in hooks and item._duration:
                            first = max(1, floor((min(sample, old_sample)-start-item._delay)/item._duration))
                            last = min(item._loops, floor((max(sample, old_sample)-start-item._delay)/item._duration))
                            points.extend(start + item._delay + loop*item._duration for loop in range(first, last+1))
                        elif "complete" in hooks:
                            points.append(start + item.full_duration)
                        callback = None
                    elif (sample < old_sample) == (progress < self._last_progress):
                        points, callback = (start,), item
                    else:
                        continue
                    for point in set(points):
                        if ((old_sample < point <= sample) or (sample <= point < old_sample)
                                or (include_start and point == old_sample)):
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
        sample = self._ease(progress) * self._duration if sample is None else sample
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
                    if item.active and (sample >= start + item._delay or old_sample >= start + item._delay):
                        if item._seek(min(item.full_duration, max(0, sample - start)),
                                      min(item.full_duration, max(0, old_sample - start)), callbacks and sample >= start) is False:
                            return False
            self._last_sample, self._last_progress = sample, progress
            self._sample_cycle, self._sampled = cycle, True
            return True
        finally:
            self._sample_context = previous_context

    def kill(self, complete=False):
        super().kill(complete)
        for _, item in self._entries:
            if isinstance(item, Tween):
                item.kill()
        return self


class TweenManager:
    def __init__(self, on_activity=None):
        self.time_scale = 1.0
        self.unscaled_time_scale = 1.0
        self.default_update_type = UpdateType.NORMAL
        self.default_time_scale_independent = False
        self.default_auto_kill = True
        self.default_auto_play = AutoPlay.ALL
        self.default_loop_type = LoopType.RESTART
        self.default_ease_type = Ease.OUT_QUAD
        self.default_ease_overshoot_or_amplitude = 1.70158
        self.default_ease_period = 0.0
        self._tweens = {phase: {} for phase in UpdateType}
        self._running = {phase: {} for phase in UpdateType}
        self._on_activity = on_activity
        self._update_depth = 0
        self._pending_commits = {}

    def add(self, tween):
        if tween._owner is None:
            if not tween._update_configured and tween.update_type == UpdateType.NORMAL:
                tween.update_type, tween.independent = self.default_update_type, self.default_time_scale_independent
            if not tween._ease_configured and not isinstance(tween, Sequence):
                tween._ease_source = self.default_ease_type
                tween._ease_args = self.default_ease_overshoot_or_amplitude, self.default_ease_period
                tween._ease = resolve_ease(tween._ease_source, *tween._ease_args, duration=lambda: tween._ease_duration)
            if not tween._auto_kill_configured:
                tween.auto_kill = self.default_auto_kill
            if not tween._loops_configured:
                tween.loop_type = self.default_loop_type
            tween.playing = (self.default_auto_play == AutoPlay.ALL
                             or self.default_auto_play == (AutoPlay.AUTO_PLAY_SEQUENCES if isinstance(tween, Sequence)
                                                          else AutoPlay.AUTO_PLAY_TWEENERS))
        tween._owner = self
        group = self._tweens[tween.update_type]
        group[tween] = None
        if tween.playing:
            self._resume(tween)
        return tween

    @overload
    def to(self, getter: Callable[[], object], setter: Callable[[object], None], end_value: object, duration: float): ...
    @overload
    def to(self, setter: Callable[[float], None], start_value: float, end_value: float, duration: float): ...
    def to(self, *args, **kwargs):
        virtual = ("start_value" in kwargs or (len(args) >= 2 and not callable(args[1]))
                   or (not args and "getter" not in kwargs))
        names = ("setter", "start_value", "end_value", "duration") if virtual else ("getter", "setter", "end_value", "duration")
        values = _bind_arguments(names, args, kwargs)
        if virtual:
            setter, start, end_value, duration = values
            state = [start]
            def write(value):
                state[0] = value
                setter(value)
            tween = self._to(lambda: state[0], write, end_value, duration)
            tween._no_from = True
            return tween
        return self._to(*values)

    def _to(self, getter, setter, end_value, duration):
        from infernux.lib import Vector2, Vector3, vec4f, quatf
        if isinstance(end_value, str):
            from .string import StringTweener
            return self.add(StringTweener(getter, setter, end_value, duration))
        if isinstance(end_value, quatf):
            from .rotation import QuaternionTweener
            return self.add(QuaternionTweener(getter, setter, end_value, duration))
        kind = (_ColorTweener if isinstance(end_value, list) and len(end_value) == 4 else
                _VectorTweener if isinstance(end_value, (Vector2, Vector3, vec4f, tuple, list)) else _FloatTweener)
        return self.add(kind(getter, setter, end_value, duration))

    def to_axis(self, getter, setter, end_value, duration, axis_constraint=AxisConstraint.X):
        from infernux.lib import Vector3
        if not isinstance(axis_constraint, AxisConstraint):
            raise TypeError("axis_constraint must be AxisConstraint")
        return self._to(getter, setter, Vector3(end_value, end_value, end_value), duration).set_options(axis_constraint)

    def to_alpha(self, getter, setter, end_value, duration):
        return self._to(getter, setter, [0.0, 0.0, 0.0, end_value], duration).set_options(True)

    def to_array(self, getter, setter, end_values, durations):
        return self.add(_ArrayTweener(getter, setter, end_values, durations))

    def punch(self, getter, setter, direction, duration, vibrato=10, elasticity=1):
        from .motion import _punch_tween
        tween = _punch_tween(getter, setter, direction, duration, vibrato, elasticity)
        return None if tween is None else self.add(tween)

    def shake(self, getter, setter, duration, *args, **kwargs):
        from .motion import _shake_tween
        tween = _shake_tween(getter, setter, duration, *args, **kwargs)
        return None if tween is None else self.add(tween)

    @overload
    def sequence(self): ...
    @overload
    def sequence(self, target: object): ...
    def sequence(self, target=_UNSET):
        sequence = self.add(Sequence())
        return sequence if target is _UNSET else sequence.set_target(target)

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

    def update(self, delta, unscaled_delta=None, update_type=UpdateType.NORMAL):
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
                    tween._advance((unscaled * self.unscaled_time_scale if tween.independent else delta) * self.time_scale)
                except Exception:
                    tween.kill()
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

    def manual_update(self, delta_time, unscaled_delta_time):
        self.update(delta_time, unscaled_delta_time, UpdateType.MANUAL)

    def _matching(self, target_or_id=_UNSET, id=_UNSET):
        if target_or_id is None:
            return ()
        return tuple(tween for group in self._tweens.values() for tween in group
                     if ((tween.target is target_or_id and tween.id == id) if id is not _UNSET else
                         target_or_id is _UNSET or tween.target is target_or_id or tween.id == target_or_id))

    def _control(self, action, target_or_id=_UNSET, *args, id=_UNSET):
        matching = self._matching(target_or_id, id)
        affected = 0
        for tween in matching:
            if action == 'pause' and not tween.playing:
                continue
            if action == 'play' and tween.playing:
                continue
            if action == 'complete' and (tween._loops == -1 or tween.is_complete()):
                continue
            getattr(tween, action)(*args)
            affected += 1
        return affected

    def _play_control(self, action, args, kwargs):
        paired = len(args) > 1 or 'target' in kwargs or 'id' in kwargs
        names = ('target', 'id') if paired else ('target_or_id',)
        values = _bind_arguments(names, args, kwargs)
        return self._control(action, values[0], id=values[1] if paired else _UNSET)

    def play_all(self): return self._control('play')
    @overload
    def play(self, target_or_id: object): ...
    @overload
    def play(self, target: object, id: object): ...
    def play(self, *args, **kwargs): return self._play_control('play', args, kwargs)
    def play_forward_all(self): return self._control('play_forward')
    @overload
    def play_forward(self, target_or_id: object): ...
    @overload
    def play_forward(self, target: object, id: object): ...
    def play_forward(self, *args, **kwargs): return self._play_control('play_forward', args, kwargs)
    def play_backwards_all(self): return self._control('play_backwards')
    @overload
    def play_backwards(self, target_or_id: object): ...
    @overload
    def play_backwards(self, target: object, id: object): ...
    def play_backwards(self, *args, **kwargs): return self._play_control('play_backwards', args, kwargs)
    def pause_all(self): return self._control('pause')
    def pause(self, target_or_id): return self._control('pause', target_or_id)
    def flip_all(self): return self._control('flip')
    def flip(self, target_or_id): return self._control('flip', target_or_id)
    def restart_all(self, include_delay=True): return self._control('restart', _UNSET, include_delay)
    @overload
    def restart(self, target_or_id: object, include_delay: bool=True, change_delay_to: float=-1): ...
    @overload
    def restart(self, target: object, id: object, include_delay: bool=True, change_delay_to: float=-1): ...
    def restart(self, *args, **kwargs):
        paired = ('target' in kwargs or 'id' in kwargs or len(args) > 3
                  or (len(args) >= 2 and type(args[1]) is not bool)
                  or (len(args) == 3 and type(args[2]) is bool))
        names = ('target', 'id', 'include_delay', 'change_delay_to') if paired else ('target_or_id', 'include_delay', 'change_delay_to')
        values = _bind_arguments(names, args, kwargs, {'include_delay': True, 'change_delay_to': -1})
        return self._control('restart', values[0], *values[2 if paired else 1:], id=values[1] if paired else _UNSET)
    def rewind_all(self, include_delay=True): return self._control('rewind', _UNSET, include_delay)
    def rewind(self, target_or_id, include_delay=True): return self._control('rewind', target_or_id, include_delay)
    def smooth_rewind_all(self): return self._control('smooth_rewind')
    def smooth_rewind(self, target_or_id): return self._control('smooth_rewind', target_or_id)
    def toggle_pause_all(self): return self._control('toggle_pause')
    def toggle_pause(self, target_or_id): return self._control('toggle_pause', target_or_id)
    def complete_all(self, with_callbacks=False): return self._control('complete', _UNSET, with_callbacks)
    def complete(self, target_or_id, with_callbacks=False): return self._control('complete', target_or_id, with_callbacks)
    def kill_all(self, complete=False, *ids_or_targets_to_exclude):
        matching = [t for t in self._matching() if not any(t.target is item or t.id == item for item in ids_or_targets_to_exclude)]
        for tween in matching:
            tween.kill(complete)
        return len(matching)
    @overload
    def kill(self, target_or_id: object, complete: bool=False): ...
    @overload
    def kill(self, target: object, id: object, complete: bool=False): ...
    def kill(self, *args, **kwargs):
        paired = ('target' in kwargs or 'id' in kwargs or len(args) == 3
                  or (len(args) == 2 and type(args[1]) is not bool))
        names = ('target', 'id', 'complete') if paired else ('target_or_id', 'complete')
        values = _bind_arguments(names, args, kwargs, {'complete': False})
        return self._control('kill', values[0], values[-1], id=values[1] if paired else _UNSET)
    def goto_all(self, to, and_play=False): return self._control('goto', _UNSET, to, and_play)
    def goto(self, target_or_id, to, and_play=False): return self._control('goto', target_or_id, to, and_play)

    def is_tweening(self, target_or_id, also_check_if_is_playing=False):
        return any(not also_check_if_is_playing or tween.playing for tween in self._matching(target_or_id))

    def tweens_by_id(self, id, playing_only=False, fillable_list=None):
        return _fill_list((tween for tween in self._matching(id)
                           if tween.id == id and (not playing_only or tween.playing)), fillable_list)

    def tweens_by_target(self, target, playing_only=False, fillable_list=None):
        return _fill_list((tween for tween in self._matching(target)
                           if tween.target is target and (not playing_only or tween.playing)), fillable_list)

    def playing_tweens(self, fillable_list=None):
        return _fill_list((tween for tween in self._matching() if tween.playing), fillable_list)

    def paused_tweens(self, fillable_list=None):
        return _fill_list((tween for tween in self._matching() if not tween.playing), fillable_list)

    def total_active_tweens(self): return sum(map(len, self._tweens.values()))
    def total_active_tweeners(self): return sum(not isinstance(tween, Sequence) for tween in self._matching())
    def total_active_sequences(self): return sum(isinstance(tween, Sequence) for tween in self._matching())
    def total_tweens_by_id(self, id, playing_only=False):
        return sum(tween.id == id and (not playing_only or tween.playing) for tween in self._matching(id))
    def total_playing_tweens(self): return sum(map(len, self._running.values()))

    def get_diagnostics(self):
        phases = {phase.name: {"active": len(self._tweens[phase]), "playing": len(self._running[phase])}
                  for phase in UpdateType}
        return {"active": sum(item["active"] for item in phases.values()),
                "playing": sum(item["playing"] for item in phases.values()), "phases": phases}

    def clear(self, destroy=False):
        for group in self._tweens.values():
            for tween in tuple(group):
                tween.kill()
        if destroy:
            self.__init__(self._on_activity)


def _fill_list(items, fillable_list):
    result = [] if fillable_list is None else fillable_list
    result.clear()
    result.extend(items)
    return result if result or fillable_list is not None else None


def _bind_arguments(names, args, kwargs, defaults=None):
    if len(args) > len(names) or any(name not in names for name in kwargs):
        raise TypeError("invalid overload arguments")
    values = dict(zip(names, args))
    if values.keys() & kwargs.keys():
        raise TypeError("duplicate argument")
    values.update(kwargs)
    for name, value in (defaults or {}).items():
        values.setdefault(name, value)
    if len(values) != len(names):
        raise TypeError(f"required arguments: {', '.join(name for name in names if name not in values)}")
    return tuple(values[name] for name in names)


class TweenParams:
    def __init__(self):
        self.clear()

    def clear(self):
        self._settings = Tween(0)
        self._settings._ease_source = Ease.UNSET
        return self

    def _set(self, name, *args, **kwargs):
        getattr(self._settings, name)(*args, **kwargs)
        return self

    def set_id(self, object_id): return self._set("set_id", object_id)
    def set_auto_kill(self, auto_kill_on_completion=True): return self._set("set_auto_kill", auto_kill_on_completion)
    def set_loops(self, loops, loop_type=_UNSET): return self._set("set_loops", loops, loop_type)
    def set_delay(self, delay): return self._set("set_delay", delay)
    def set_relative(self, is_relative=True): return self._set("set_relative", is_relative)
    def set_update(self, *args, **kwargs): return self._set("set_update", *args, **kwargs)
    def set_ease(self, *args, **kwargs): return self._set("set_ease", *args, **kwargs)
    def set_speed_based(self, is_speed_based=True):
        self._settings._speed_based = is_speed_based
        return self
    def on_start(self, action): return self._set("on_start", action)
    def on_play(self, action): return self._set("on_play", action)
    def on_rewind(self, action): return self._set("on_rewind", action)
    def on_update(self, action): return self._set("on_update", action)
    def on_step_complete(self, action): return self._set("on_step_complete", action)
    def on_complete(self, action): return self._set("on_complete", action)
    def on_kill(self, action): return self._set("on_kill", action)
    def on_waypoint_change(self, action): return self._set("_on", "waypoint", action)


_default_manager = TweenManager()
