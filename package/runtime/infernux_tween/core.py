"""Shared playback, seeking and sequence timing."""

from enum import Enum, IntFlag
from functools import cached_property, partial, wraps
from heapq import heappop, heappush
from math import floor, inf, isfinite, sqrt
from operator import attrgetter
from typing import Callable, TypeVar, overload, TYPE_CHECKING

from infernux.graph.ramp import AnimationCurve

from .ease import Ease, resolve_ease, native_ease_kernel, time_ease_sampler
from .yield_instruction import (
    WaitForCompletion, WaitForKill, WaitForStart, WaitForRewind, WaitForElapsedLoops, WaitForPosition,
)
from infernux.lib._Infernux import (
    _ScalarTweenSnapshot, _SignedIntegerTweenSnapshot, _LiveVector2TweenSnapshot, _LiveVector3TweenSnapshot,
    _LiveVector4TweenSnapshot, _LiveColorTweenSnapshot, _round_tween_value,
    _tween_float32 as _f32, _advance_tween_clock, _exceptional_tween_clock,
    _advance_exceptional_tween_clock, _compile_tween_clock,
    _TweenNumericOverflow, _TweenPlaybackClock,
)
from infernux.lib import Vector2, Vector3, vec4f
from .color import _ColorValue, _color_value

_VECTOR_SNAPSHOTS = {Vector2: _LiveVector2TweenSnapshot, Vector3: _LiveVector3TweenSnapshot, vec4f: _LiveVector4TweenSnapshot}


def _copy_vector(value):
    return type(value)(*value) if type(value) in _VECTOR_SNAPSHOTS else value


def _snap_value(value, integer, constraint, value_type, sequence_value, all_channels=False):
    if isinstance(value, (int, float)):
        return round(value) if integer else _round_tween_value(value)
    if type(value) in _VECTOR_SNAPSHOTS:
        return _round_tween_value(value, 0 if all_channels else int(constraint))
    values = [_round_tween_value(item) if all_channels or not constraint or constraint & (2 << i) else item
              for i, item in enumerate(value)]
    return value_type(values) if sequence_value else value_type(*values)

if TYPE_CHECKING:
    from .plugin import AbsTweenPlugin
    from .motion import ShakeRandomnessMode

_UNSET = object()
_Value = TypeVar('_Value')
_DEFAULT_EASE_ARGS = (_f32(1.70158), 0.0)
_MIN_FRAME_STEP = _f32(1e-6)


def _single_field(storage):
    def assign(self, value):
        setattr(self, storage, _f32(value))
    return property(attrgetter(storage), assign)
def _is_int_id(value):
    return type(value) is int and -(2**31) <= value < 2**31


def _id_assignment(args, kwargs):
    """Dispatch reference overloads while keeping boxed-object IDs expressible."""
    if len(args) == 1 and not kwargs:
        value = args[0]
        name = "string_id" if value is None or isinstance(value, str) else "int_id" if _is_int_id(value) else "id"
    elif not args and len(kwargs) == 1:
        key, value = next(iter(kwargs.items()))
        if key not in ("object_id", "string_id", "int_id"):
            raise TypeError("set_id expects object_id, string_id or int_id")
        name = "id" if key == "object_id" else key
    else:
        raise TypeError("set_id expects exactly one ID")
    if name == "string_id" and value is not None and not isinstance(value, str):
        raise TypeError("string_id must be str or None")
    if name == "int_id":
        if type(value) is not int:
            raise TypeError("int_id must be int")
        if not -(2**31) <= value < 2**31:
            raise OverflowError("int_id must fit a signed 32-bit integer")
    return name, value


def _callback_field(name):
    def assign(self, callback):
        if callback is not None and not callable(callback):
            raise TypeError("callback must be callable or None")
        self._callbacks[name] = callback
    return property(lambda self: self._callbacks.get(name), assign)


def _root_control(command):
    """Public commands belong to live roots; owners use internal execution."""
    returns_none = command.__annotations__.get("return", _UNSET) is None
    @wraps(command)
    def invoke(self, *args, **kwargs):
        if not self._active:
            return self._inactive_value(None if returns_none else self, control=True)
        if self._parent is None:
            return command(self, *args, **kwargs)
        return None if returns_none else self
    return invoke


class _NestedTweenFailure(Exception):
    """A reported child failure that must pass through each ancestor policy."""


class _EvaluationFailure(Exception):
    """A reported evaluation failure with caller-specific retirement."""


class _StartupDeclined(Exception):
    """A special initializer returned false without a Safe Mode error."""


class NestedTweenFailureBehaviour(Enum):
    TRY_TO_PRESERVE_SEQUENCE = 0
    KILL_WHOLE_SEQUENCE = 1


class LogBehaviour(Enum):
    DEFAULT = 0
    VERBOSE = 1
    ERRORS_ONLY = 2


class RewindCallbackMode(Enum):
    FIRE_IF_POSITION_CHANGED = 0
    FIRE_ALWAYS_WITH_REWIND = 1
    FIRE_ALWAYS = 2


class SafeModeLogBehaviour(Enum):
    NONE = 0
    NORMAL = 1
    WARNING = 2
    ERROR = 3


class LoopType(Enum):
    RESTART = 0
    YOYO = 1
    INCREMENTAL = 2


class UpdateType(Enum):
    NORMAL = 0
    LATE = 1
    FIXED = 2
    MANUAL = 3

    @property
    def engine_phase(self):
        return ("update", "late_update", "fixed_update", "manual")[self.value]


class _DispatchCursor:
    __slots__ = ('phase', 'limit', 'order', 'pending')

    def __init__(self, phase, limit):
        self.phase, self.limit, self.order, self.pending = phase, limit, -1, None

    def resume(self, tween):
        order = tween._dispatch_order
        if self.phase == tween.update_type and self.order < order < self.limit:
            if self.pending is None:
                self.pending = []
            heappush(self.pending, (order, tween, tween._generation))

    def entries(self, snapshot):
        for entry in snapshot:
            order = entry[0]
            while self.pending and self.pending[0][0] <= order:
                pending = heappop(self.pending)
                if pending[0] > self.order:
                    self.order = pending[0]
                    yield pending
            if order > self.order:
                self.order = order
                yield entry
        while self.pending:
            pending = heappop(self.pending)
            if pending[0] > self.order:
                self.order = pending[0]
                yield pending


class AutoPlay(Enum):
    NONE = 0
    ALL = 3
    AUTO_PLAY_SEQUENCES = 1
    AUTO_PLAY_TWEENERS = 2


class AxisConstraint(IntFlag):
    NONE = 0
    X = 2
    Y = 4
    Z = 8
    W = 16


class OnEnableBehaviour(Enum):
    NONE = 0
    PLAY = 1
    RESTART = 2
    RESTART_FROM_SPAWN_POINT = 3


class OnDisableBehaviour(Enum):
    NONE = 0
    PAUSE = 1
    REWIND = 2
    KILL = 3
    KILL_AND_COMPLETE = 4
    DESTROY_GAME_OBJECT = 5


class VisualManagerPreset(Enum):
    CUSTOM = 0
    POOLING_SYSTEM = 1


class Tween:
    time_scale = _single_field('_time_scale')

    def __init__(self, duration):
        self._generation = getattr(self, "_generation", 0) + 1
        self.recyclable = False
        self._recyclable_configured = False
        self._duration = _f32(duration)
        self._delay = 0.0
        self._loops = 1
        self._clock_duration = self._classified_duration = None
        self._update_clock_kind()
        self.loop_type = LoopType.RESTART
        self._time_scale = 1.0
        self.auto_kill = True
        self.playing = True
        self._active = True
        self._position = 0.0
        self._waypoint = -1
        # A zero-length clock still has logical loop/rewind states. Goto and
        # normal playback do not advance these states in the same way.
        self._zero_completed_loops = 0
        self._zero_elapsed_nan = False
        self.target = None
        self.id = None
        self.string_id = None
        self.int_id = -999
        self.debug_target_id = None
        self.update_type = UpdateType.NORMAL
        self.independent = False
        self._parent = None
        self._owner = None
        self._callback_manager = None
        self._started = False
        self._play_pending = True
        self._locked = False
        self._initialized = False
        self._backwards = False
        retained_pause = getattr(self, "_callbacks", {}).get("pause")
        self._callbacks = {} if retained_pause is None else {"pause": retained_pause}
        self._waiters = []
        self._speed_based = False
        self._link = None
        self._seek_serial = 0
        self._inverted = False
        self._relative = False
        self._ease_source = Ease.OUT_QUAD
        self._ease_args = _DEFAULT_EASE_ARGS
        self._ease_configured = False
        self._update_configured = False
        self._auto_kill_configured = False
        self._loops_configured = False
        self._assign_ease(resolve_ease(self._ease_source, *self._ease_args, duration=lambda: self._duration))

    def _assign_ease(self, sampler):
        self._ease = sampler
        self._numeric_ease = native_ease_kernel(sampler)
        self.__dict__.pop('_ease_time', None)
        bind = getattr(self, "_bind_numeric_sampler", None)
        if bind is not None:
            bind()

    @cached_property
    def _ease_time(self):
        return time_ease_sampler(self._ease, self._numeric_ease, self._ease_source, self._ease_args)

    def _update_clock_kind(self):
        duration = self._duration
        if duration is self._classified_duration:
            return
        self._classified_duration = duration
        if duration is not self._clock_duration:
            self._refresh_full_duration()
        exceptional = not (duration == 0 or 1.1754943508222875e-38 <= duration < inf)
        self._has_clock_state = duration == 0 or exceptional
        self._exceptional_clock = exceptional
        if exceptional:
            self._progress_at = self._exceptional_progress_at
            self._advance = self._advance_exceptional
        else:
            self.__dict__.pop('_progress_at', None)
            if duration == 0:
                self._advance = self._advance_zero
            else:
                self.__dict__.pop('_advance', None)

    @property
    def full_duration(self):
        return self._full_duration

    def _refresh_full_duration(self):
        self._sample_clock, self._playback_duration, self._full_duration = _compile_tween_clock(
            self._duration, self._delay, self._loops)
        self._clock_duration = self._duration
        self._phase_clock = (_TweenPlaybackClock(self._duration, self._delay, self._loops,
                                                self.__dict__.get('_position', 0.))
                             if 1.1754943508222875e-38 <= self._duration < inf else None)
        self._sample_playback_clock = self._phase_clock.sample if self._phase_clock is not None else self._sample_clock
        self._update_clock_kind()

    def _set_clock_position(self, position):
        self._position = position
        if self._phase_clock is not None:
            self._phase_clock.seek(position)

    @property
    def _ease_duration(self):
        return self._duration

    @property
    def full_position(self) -> float:
        return self.elapsed()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def position(self) -> float:
        if self._phase_clock is not None:
            return self._phase_clock.position
        if self._position == self._full_duration and self._duration > 0 and self._loops > 0:
            return self._duration
        elapsed = self._position - self._delay
        if self._position >= 0 and elapsed < 0:
            elapsed = 0.0
        if self._has_clock_state:
            return float("nan") if self._duration == 0 and self._zero_elapsed_nan else _f32(elapsed)
        return self._duration if elapsed > 0 and elapsed % self._duration == 0 else _f32(elapsed % self._duration)

    @property
    def has_loops(self):
        return self._loops == -1 or self._loops > 1

    @property
    def is_relative(self):
        return self._relative

    @property
    def played_once(self):
        return self._started

    # C# distinguishes callback fields (onPlay) and extensions (OnPlay) by case.
    # Keep fluent on_play(...) and expose its raw delegate as play_callback.
    start_callback = _callback_field("start")
    play_callback = _callback_field("play")
    pause_callback = _callback_field("pause")
    rewind_callback = _callback_field("rewind")
    update_callback = _callback_field("update")
    step_complete_callback = _callback_field("step")
    complete_callback = _callback_field("complete")
    kill_callback = _callback_field("kill")
    waypoint_change_callback = _callback_field("waypoint")

    @property
    def backwards(self):
        return self._backwards

    @backwards.setter
    def backwards(self, value):
        if type(value) is not bool:
            raise TypeError("backwards must be bool")
        self._backwards = value

    @property
    def ease_overshoot_or_amplitude(self):
        return self._ease_args[0]

    @ease_overshoot_or_amplitude.setter
    def ease_overshoot_or_amplitude(self, value):
        self._ease_args = (_f32(value), self._ease_args[1])
        self._assign_ease(resolve_ease(self._ease_source, *self._ease_args, duration=lambda: self._ease_duration))

    @property
    def ease_period(self):
        return self._ease_args[1]

    @ease_period.setter
    def ease_period(self, value):
        self._ease_args = (self._ease_args[0], _f32(value))
        self._assign_ease(resolve_ease(self._ease_source, *self._ease_args, duration=lambda: self._ease_duration))

    @full_position.setter
    def full_position(self, value: float) -> None:
        self.goto(value, self.playing)

    def _configure(self):
        return self._active and not self._locked and self._parent is None

    @overload
    def set_delay(self, delay: float): ...
    @overload
    def set_delay(self, delay: float, as_prepended_interval_if_sequence: bool): ...
    def set_delay(self, delay: float, as_prepended_interval_if_sequence=_UNSET):
        if not self._configure():
            return self
        delay = _f32(delay)
        if not isfinite(delay) or delay < 0:
            raise ValueError("Delay must be finite and nonnegative")
        self._delay = delay
        self._refresh_full_duration()
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
        self._refresh_full_duration()
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

    def set_recyclable(self, recyclable=True):
        if self._active:
            self.recyclable = bool(recyclable)
            self._recyclable_configured = True
        return self

    @overload
    def set_id(self, object_id: object): ...
    @overload
    def set_id(self, *, string_id: str | None): ...
    @overload
    def set_id(self, *, int_id: int): ...
    def set_id(self, *args, **kwargs):
        name, value = _id_assignment(args, kwargs)
        if self._active:
            setattr(self, name, value)
        return self

    def set_target(self, target: object):
        if not self._active:
            return self
        if (self._owner or _default_manager).debug_store_target_id:
            if target is None:
                raise TypeError("a debug target must not be None")
            owner = getattr(target, "game_object", None)
            self.debug_target_id = owner.name if owner is not None else str(target)
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
        amplitude, period = self._ease_args
        numeric_options = bool(args) or any(name in kwargs for name in ("overshoot", "amplitude", "period"))
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
        if kwargs or ease is _UNSET or (not isinstance(ease, Ease) and numeric_options):
            raise TypeError("invalid set_ease overload")
        amplitude, period = _f32(amplitude), _f32(period)
        self._ease_source, self._ease_args = ease, (amplitude, period)
        self._assign_ease(resolve_ease(ease, amplitude, period, lambda: self._ease_duration))
        self._ease_configured = True
        return self

    @overload
    def set_as(self, as_tween: "Tween"): ...
    @overload
    def set_as(self, tween_params: "TweenParams"): ...
    def set_as(self, as_tween=_UNSET, *, tween_params=_UNSET):
        if tween_params is not _UNSET:
            if as_tween is not _UNSET:
                raise TypeError("set_as accepts one source")
            as_tween = tween_params
        if not self._configure():
            return self
        parameters = isinstance(as_tween, TweenParams)
        source = as_tween._settings if parameters else as_tween
        if not isinstance(source, Tween):
            raise TypeError("set_as expects Tween or TweenParams")
        if not parameters:
            self._time_scale, self._backwards = source._time_scale, source._backwards
        self.set_update(source.update_type, source.independent)
        self.id = source.id
        self.string_id, self.int_id = source.string_id, source.int_id
        for name in ("start", "play", "rewind", "update", "step", "complete", "kill", "waypoint"):
            self._callbacks[name] = source._callbacks.get(name)
        self.recyclable, self._recyclable_configured = source.recyclable, True
        self.auto_kill, self._loops, self.loop_type = source.auto_kill, source._loops, source.loop_type
        self._auto_kill_configured = self._loops_configured = True
        self._delay, self._speed_based = source._delay, source._speed_based
        self._refresh_full_duration()
        self._set_relative(source._relative)
        ease = source._ease_source
        if ease == Ease.UNSET:
            ease = Ease.LINEAR if isinstance(self, Sequence) else (self._owner or _default_manager).default_ease_type
        self._ease_source, self._ease_args = ease, source._ease_args
        self._assign_ease(resolve_ease(ease, *source._ease_args, duration=lambda: self._ease_duration))
        return self

    def _on(self, name, callback):
        if callback is not None and not callable(callback):
            raise TypeError("callback must be callable or None")
        if self._active:
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
    def on_waypoint_change(self, action: Callable[[int], None]): return self._on("waypoint", action)

    def _emit(self, name):
        callback = self._callbacks.get(name)
        return True if callback is None else self._invoke(callback)

    def _emit_initial(self, name):
        callback = self._callbacks.get(name)
        if callback is None:
            return True
        generation = self._generation
        root = self
        while root._parent is not None:
            root = root._parent
        manager = root._callback_manager or _default_manager
        try:
            callback()
        except Exception as error:
            if not manager.use_safe_mode:
                raise
            manager._record_error(error)
        # Initial notifications run before this frame publishes its phase.
        # Seeking or pausing here does not cancel that captured frame.
        return self._active and self._generation == generation

    def _invoke(self, callback, *, pause_interrupts=True):
        states, tween = [], self
        while True:
            states.append((tween, tween._position, tween.playing, tween._seek_serial, tween._generation))
            parent = tween._parent
            if parent is None or parent._sample_context is None:
                break
            tween = parent
        manager = getattr(states[-1][0], "_callback_manager", None) or _default_manager
        try:
            callback()
        except Exception as error:
            if not manager.use_safe_mode:
                raise
            manager._record_error(error)
        stop = False
        for tween, clock, playing, serial, generation in states:
            changed = (not tween._active or tween._position != clock or tween._seek_serial != serial
                       or tween._generation != generation)
            if changed or (pause_interrupts and tween is self and tween.playing != playing):
                stop = True
            if (isinstance(tween, Sequence) and tween._generation == generation and not changed
                    and tween.playing != playing):
                # A paused owner keeps the frame's actual clock. Advance its
                # sampling cursor without inventing an earlier callback time.
                cycle, progress = tween._progress_at(clock)
                tween._sample_cycle, tween._last_progress = cycle, progress
                tween._last_sample = tween._ease_at(progress, cycle) * tween._duration
                tween._sampled = True
        return not stop

    @_root_control
    def play(self):
        self._play()
        return self

    def _play(self, backwards=None, *, notify_play=True):
        if not self._active:
            return False
        at_start = (self._zero_completed_loops == 0 if self._duration == 0
                    else 0 <= self._position <= self._delay)
        if backwards is True and at_start:
            self._rewind_callback_at_start(explicit=False)
        changed_direction = backwards is not None and self._backwards != backwards
        if backwards is not None:
            self._backwards = backwards
        at_boundary = at_start if self._backwards else self.is_complete()
        if at_boundary:
            if backwards is not None and self.playing:
                self.playing = False
                if self._owner is not None:
                    self._owner._pause(self)
            return False
        if not self.playing:
            self.playing = True
            self._play_pending = True
            if self._owner is not None:
                self._owner._resume(self)
            if self._started and self._position >= self._delay:
                self._play_pending = False
                if notify_play:
                    self._emit("play")
            return True
        return changed_direction

    @_root_control
    def pause(self):
        if self.playing:
            self.playing = False
            if self._owner is not None:
                self._owner._pause(self)
            self._emit("pause")
        return self

    @_root_control
    def play_forward(self) -> None:
        self._play(False)

    @_root_control
    def play_backwards(self) -> None:
        self._play(True)

    @_root_control
    def restart(self, include_delay: bool=True, change_delay_to: float=-1) -> None:
        was_paused = not self.playing
        self._backwards = False
        change_delay_to = _f32(change_delay_to)
        if change_delay_to >= 0:
            self._delay = change_delay_to
            self._refresh_full_duration()
        self.rewind(include_delay)
        self._play(notify_play=was_paused)

    @_root_control
    def rewind(self, include_delay: bool=True) -> None:
        if self._active and self._duration == 0:
            already_rewound = self._initialized and not self._zero_completed_loops
            if self._zero_completed_loops or self._position > 0:
                self._seek(0.0 if include_delay else self._delay, self._position, False, zero_loops=0)
            else:
                self._position = 0.0 if include_delay else self._delay
            if already_rewound:
                self._pause_at_start()
                self._rewind_callback_at_start(explicit=True)
                return
            self.pause()
            return
        if self._initialized and self._duration > 0 and self._position <= self._delay:
            self._set_clock_position(0.0 if include_delay else self._delay)
            self._pause_at_start()
            self._rewind_callback_at_start(explicit=True)
            return
        self._goto(0.0 if include_delay else self._delay)

    def _pause_at_start(self):
        self.playing = False
        if self._owner is not None:
            self._owner._pause(self)

    def _rewind_callback_at_start(self, *, explicit):
        callback = self._callbacks.get("rewind")
        if callback is None:
            return
        manager = self._owner or self._callback_manager or _default_manager
        mode = manager.rewind_callback_mode
        if mode == RewindCallbackMode.FIRE_ALWAYS or explicit and mode == RewindCallbackMode.FIRE_ALWAYS_WITH_REWIND:
            self._invoke(callback)

    @_root_control
    def flip(self) -> None:
        self._backwards = not self._backwards

    @_root_control
    def toggle_pause(self) -> None:
        self.pause() if self.playing else self.play()

    @_root_control
    def force_init(self) -> None:
        self._force_initialize()

    def _force_initialize(self):
        try:
            return self._ensure_initialized()
        except _StartupDeclined:
            # ForceInit removes a failed root from automatic scheduling, but
            # its live handle remains available to explicit Goto operations.
            if self._owner is not None:
                self._owner._remove(self)
            return self

    def _ensure_initialized(self):
        self._update_clock_kind()
        if self._duration < 0 and not self._initialized:
            self._assign_ease(resolve_ease(Ease.INTERNAL_ZERO, duration=lambda: self._duration))
        self._initialized = True
        return self

    def path_length(self) -> float:
        return -1.0

    def path_get_point(self, path_percentage: float) -> Vector3:
        return Vector3(0, 0, 0)

    def path_get_draw_points(self, subdivisions_x_segment: int=10):
        return None

    @_root_control
    def goto_waypoint(self, waypoint_index: int, and_play: bool=False) -> None:
        return

    @_root_control
    def smooth_rewind(self) -> None:
        if (self._initialized and self._position <= self._delay
                and (self._duration != 0 or not self._zero_completed_loops)):
            self._set_clock_position(self._delay)
            self._pause_at_start()
            self._rewind_callback_at_start(explicit=False)
            return
        if self._position <= self._delay:
            self.rewind(False)
            self.play_backwards()
            return
        if self.loop_type != LoopType.INCREMENTAL:
            elapsed = self.elapsed(False)
            cycle = self.completed_loops() - int(elapsed == self._duration)
            if self.loop_type == LoopType.YOYO and cycle % 2:
                elapsed = self._duration - elapsed
            self._goto(self._delay + elapsed)
        self.play_backwards()

    @_root_control
    def goto(self, to: float, and_play: bool=False) -> None:
        self._goto(self._delay + max(0.0, _f32(to)), and_play)

    @_root_control
    def goto_with_callbacks(self, to: float, and_play: bool=False) -> None:
        if self._active:
            self._force_initialize()
            self._seek_serial += 1
            if self._seek(min(self.full_duration, self._delay + max(0.0, _f32(to))), self._position, True) is not False:
                self.play() if and_play else self.pause()

    @_root_control
    def manual_update(self, delta_time: float, unscaled_delta_time: float) -> None:
        self._advance(_f32(unscaled_delta_time if self.independent else delta_time))

    def done(self):
        if self._duration == 0 and self._parent is None:
            self.complete()
        return self

    def _goto(self, position, and_play=False, *, clamp_position=True):
        if not self._active:
            return self
        self._seek_serial += 1
        serial = self._seek_serial
        self._force_initialize()
        previous = self._position
        was_playing = self.playing
        if not and_play:
            self.playing = False
            if self._owner is not None:
                self._owner._pause(self)
        if and_play and not self.playing:
            self.playing = True
            if self._owner is not None:
                self._owner._resume(self)
        if self._exceptional_clock:
            position, loops = _exceptional_tween_clock(position - self._delay, self._duration, self._loops)
            position += self._delay
        elif not clamp_position and position < 0:
            position, loops = floor(position / self._duration) * self._duration, 1
        else:
            position, loops = min(self.full_duration, max(0.0, float(position))), 1
        self._seek(position, previous, False, zero_loops=loops, zero_elapsed_nan=self._loops != 1)
        if self._seek_serial != serial:
            return self
        if not and_play and was_playing and self._active and not (self.auto_kill and self.is_complete()):
            self._emit("pause")
        if not and_play or self.is_complete():
            if self.auto_kill and self.is_complete():
                self.playing = False
                if self._owner is not None:
                    self._owner._pause(self)
            else:
                self.pause()
        return self

    @_root_control
    def complete(self, with_callbacks: bool=False) -> None:
        if self._loops != -1 and self._active:
            if self._duration == 0 and self.is_complete():
                return
            try:
                self._ensure_initialized()
            except _StartupDeclined:
                self.playing = False
                if self._owner is not None:
                    self._owner._pause(self)
                return
            if self._seek(self.full_duration, self._position, bool(with_callbacks), zero_loops=self._loops, notify_steps=False) is False:
                return
            if not self._active or self._position != self.full_duration:
                return
            if self._active and self._position == self.full_duration:
                if self.auto_kill:
                    self._kill(at_update_end=True)
                elif self._backwards:
                    self.playing = False
                    if self._owner is not None:
                        self._owner._pause(self)
                else:
                    self.pause()

    @_root_control
    def kill(self, complete: bool=False) -> None:
        self._kill(complete)

    def _kill(self, complete: bool=False, *, at_update_end=False):
        if not self._active:
            return self
        if complete and self._loops != -1:
            self.complete()
            if not self._active:
                return self
        owner = self._owner or getattr(self, "_retiring_owner", None)
        self._active = False
        if owner is not None and owner._update_depth:
            if at_update_end and owner._dispatch_contexts[-1].order == self._dispatch_order:
                owner._pending_kills[self] = self._generation
            else:
                owner._resume(self)
        else:
            self._despawn(owner)
        return self

    def _despawn(self, owner):
        if owner is not None:
            owner._pending_kills.pop(self, None)
        self.playing = False
        if self._link is not None:
            self._link.detach(self)
        if self._owner is not None:
            self._owner._remove(self)
        self._emit("kill")
        # The pinned reference resets every delegate except onPause. Preserve
        # that observable field, including typed pool reuse, rather than letting
        # a fluent method accidentally masquerade as its data counterpart.
        retained_pause = self._callbacks.get("pause")
        self._callbacks.clear()
        if retained_pause is not None:
            self._callbacks["pause"] = retained_pause
        self._notify_waiters()
        self._on_despawn()
        if owner is not None and not isinstance(self, Sequence):
            owner._recycle(self)

    def _on_despawn(self):
        self._started = self._relative = self._backwards = False
        self._set_clock_position(0.0)
        self.id = self.string_id = self.target = self.debug_target_id = None
        self.int_id = -999

    def is_active(self): return self._active
    def _inactive_value(self, value, *, control=False):
        manager = self._callback_manager or _default_manager
        if (manager.log_behaviour == LogBehaviour.ERRORS_ONLY
                or control and manager.log_behaviour != LogBehaviour.VERBOSE):
            return value
        from infernux.debug import Debug, LogType
        message = "Tween: This Tween has been killed and is now invalid"
        if manager.on_will_log is None or manager.on_will_log(LogType.WARNING, message):
            Debug.log_warning(message)
        return value

    def is_playing(self): return self.playing if self._active else self._inactive_value(False)
    def is_complete(self):
        if not self._active:
            return self._inactive_value(False)
        if self._phase_clock is not None:
            return self._phase_clock.is_complete
        return (self._loops != -1 and self._zero_completed_loops >= self._loops
                if self._has_clock_state else self._position >= self.full_duration)
    def is_backwards(self): return self._backwards if self._active else self._inactive_value(False)
    def delay(self): return self._delay if self._active else self._inactive_value(0.0)
    def elapsed_delay(self):
        if not self._active:
            return self._inactive_value(0.0)
        return self._phase_clock.elapsed_delay if self._phase_clock is not None else _f32(min(self._position, self._delay))
    def loops(self): return self._loops if self._active else self._inactive_value(0)
    def is_time_scale_independent(self): return self.independent if self._active else self._inactive_value(False)
    def is_initialized(self): return self._initialized if self._active else self._inactive_value(False)
    def elapsed_directional_percentage(self):
        if not self._active:
            return self._inactive_value(0.0)
        if not self._duration:
            return float("nan")
        progress = _f32(self.elapsed(False) / self._duration)
        cycle = self.completed_loops() - int(self.is_complete())
        return _f32(1 - progress) if self.has_loops and self.loop_type == LoopType.YOYO and cycle % 2 else progress
    def is_looping_or_executing_backwards(self):
        if not self._active:
            return self._inactive_value(False)
        return self._backwards != (self.loop_type == LoopType.YOYO and self.completed_loops() % 2 == 1)
    def completed_loops(self):
        if not self._active:
            return self._inactive_value(0)
        if self._phase_clock is not None:
            return self._phase_clock.completed_loops
        return (self._zero_completed_loops if self._has_clock_state else
                floor((self._position - self._delay if self._position < 0 else max(0.0, self._position - self._delay)) / self._duration))
    def duration(self, include_loops: bool=True):
        if not self._active:
            return self._inactive_value(0.0)
        return self._playback_duration if include_loops else self._duration
    def elapsed_percentage(self, include_loops: bool=True):
        if not self._active:
            return self._inactive_value(0.0)
        if self._duration == 0:
            if not include_loops:
                return float("nan")
            return self.elapsed() / inf if self._loops == -1 else 0.0
        duration = self.duration(include_loops)
        return _f32(self.elapsed(include_loops) / duration) if 0 < duration < inf else 0.0
    def elapsed(self, include_loops: bool=True):
        if not self._active:
            return self._inactive_value(0.0)
        if not include_loops:
            return self.position
        if self._phase_clock is not None:
            return self._phase_clock.elapsed
        if self._duration == 0:
            return float("nan") if self._zero_elapsed_nan else 0.0
        elapsed = self._position - self._delay if self._position < 0 else max(0.0, self._position - self._delay)
        return _f32(elapsed)

    def _progress_at(self, position):
        return self._sample_playback_clock(position, self.loop_type == LoopType.YOYO, self._inverted)

    def _completed_loops_at(self, position):
        if self._phase_clock is not None:
            return self._phase_clock.completed_at(position)
        return floor((position - self._delay if position < 0 else max(0., position - self._delay)) / self._duration)

    def _is_complete_at(self, position):
        if self._phase_clock is not None:
            return self._phase_clock.complete_at(position)
        return self._loops != -1 and position >= self.full_duration

    def _exceptional_progress_at(self, position):
        progress = (1.0 if self._duration <= 0 else (position - self._delay) / self._duration)
        cycle = self._zero_completed_loops - int(progress == 1)
        if self.loop_type == LoopType.YOYO and cycle % 2:
            progress = 1 - progress
        return cycle, 1 - progress if self._inverted else progress

    def _is_rewind_step(self, previous):
        if previous <= self._delay:
            return False
        if self._position <= self._delay:
            return True
        return (self._duration > 0 and self.loop_type == LoopType.RESTART
                and self.completed_loops() != self._completed_loops_at(previous)
                and not self.is_complete())

    def _incremental_cycles(self, cycle, include_parent=True):
        offset = 0
        if self.loop_type == LoopType.INCREMENTAL:
            offset = self.completed_loops() - int(self.is_complete())
        if include_parent and (parent := self._parent) is not None and parent.loop_type == LoopType.INCREMENTAL:
            # Only the immediate parent's increment is part of this plugin's
            # value. Enclosing sequences drive its timeline, not another offset.
            offset += parent._incremental_cycles(0, False) * (self._loops if self.loop_type == LoopType.INCREMENTAL else 1)
        return offset

    def _completed_steps(self, previous, was_complete, backwards):
        old_loops = self._completed_loops_at(previous)
        new_loops = self.completed_loops()
        if backwards:
            steps = old_loops - new_loops if new_loops < old_loops else int(
                (self._position - self._delay) % self._duration == 0 and (
                    previous > self._delay or previous < 0 and previous % self._duration != 0))
            return steps - int(was_complete)
        return max(0, new_loops - old_loops)

    def _seek(self, position, previous, callbacks, *, notify_update=True, zero_loops=None, zero_elapsed_nan=False, notify_steps=True, retire_on_error=False, advancing=False):
        try:
            return self._seek_unchecked(position, previous, callbacks, notify_update,
                                        zero_loops, zero_elapsed_nan, notify_steps, advancing)
        except _StartupDeclined:
            if self._parent is not None:
                raise
            if retire_on_error:
                self._kill(at_update_end=True)
            return False
        except _NestedTweenFailure:
            if self._parent is not None:
                raise
            self._kill(at_update_end=True)
            return False
        except _EvaluationFailure:
            # Goto preserves the failed handle; frame execution retires it.
            if self._parent is not None:
                raise
            if retire_on_error:
                self._kill(at_update_end=True)
            return False

    def _seek_unchecked(self, position, previous, callbacks, notify_update=True, zero_loops=None, zero_elapsed_nan=False, notify_steps=True, advancing=False):
        was_complete = self._phase_clock.was_complete if advancing else self.is_complete()
        old_zero_loops, was_zero_nan = self._zero_completed_loops, self._zero_elapsed_nan
        if not self._initialized:
            self._ensure_initialized()
        self._locked = True
        staged_clock = None
        if (callbacks and (not self._started or self._play_pending)
                and (position < 0 or position >= self._delay or self._exceptional_clock)):
            first_play = not self._started
            if advancing and ((not self._started and self._callbacks.get("start") is not None)
                              or (self._play_pending and self._callbacks.get("play") is not None)):
                staged_clock = self._phase_clock
                self._position = staged_clock.begin_callbacks()
            if not self._started:
                self._started = True
                if not self._emit_initial("start"):
                    return False
            if first_play or self._play_pending:
                self._play_pending = False
                if not self._emit_initial("play"):
                    return False
            if staged_clock is not None:
                previous = self._position
                was_complete = self.is_complete()
                old_zero_loops, was_zero_nan = self._zero_completed_loops, self._zero_elapsed_nan
        if staged_clock is not None:
            position = staged_clock.finish_callbacks(self._phase_clock)
        if self._has_clock_state:
            if zero_loops is None:
                zero_loops = (1 if self._duration == 0 else
                              _exceptional_tween_clock(position - self._delay, self._duration, self._loops)[1])
            self._zero_completed_loops = zero_loops
            self._zero_elapsed_nan = zero_elapsed_nan
        self._position = position
        if not advancing and self._phase_clock is not None:
            self._phase_clock.seek(position)
        cycle, progress = self._progress_at(position)
        backwards = self._backwards
        finished_playing = self.playing and (
            (not backwards and self.is_complete())
            or (backwards and position <= self._delay and self.completed_loops() == 0))
        if finished_playing:
            self.playing = False
            if self._owner is not None:
                self._owner._pause(self)
        try:
            applied = self._apply(progress, cycle, previous, callbacks)
        except (_NestedTweenFailure, _EvaluationFailure, _StartupDeclined):
            raise
        except Exception as error:
            root = self
            while root._parent is not None:
                root = root._parent
            manager = root._owner or root._callback_manager or _default_manager
            if not manager.use_safe_mode:
                raise
            manager._record_error(error)
            raise _EvaluationFailure() from error
        if self._waiters:
            self._notify_waiters()
        if applied is False:
            return False
        if notify_update and (update_callback := self._callbacks.get("update")) is not None:
            if not self._invoke(update_callback):
                return False
        if ((self._duration == 0 and old_zero_loops > 0 and self._zero_completed_loops == 0)
                or (self._duration > 0 and (
                    previous > self._delay and position <= self._delay
                    or previous < 0 and position == 0 and previous % self._duration != 0))):
            if not self._emit("rewind"):
                return False
        if not self._active:
            return
        # Read after OnUpdate: it can install a step callback for this crossing.
        # With no listener there is no event work, even across many cycles.
        if callbacks and notify_steps and self._duration and self._callbacks.get("step") is not None:
            for _ in range(self._completed_steps(previous, was_complete, backwards)):
                if not self._emit("step"):
                    return False
                if not self._active:
                    return
        if callbacks and notify_steps and self._duration == 0 and self._callbacks.get("step") is not None:
            steps = 1 if was_zero_nan else abs(self._zero_completed_loops - old_zero_loops)
            for _ in range(steps):
                if not self._emit("step"):
                    return False
        completed = not was_complete and self.is_complete()
        if completed and not self._emit("complete"):
            return False
        if finished_playing and not (self.auto_kill and self.is_complete()):
            self._emit("pause")

    def _advance(self, delta):
        if not self._active or not self.playing:
            return
        self._locked = True
        clock = self._phase_clock
        if not self._initialized:
            step = clock.begin_step(delta, self._time_scale)
            self._position = clock.time
            if step is None:
                return
            try:
                self._ensure_initialized()
            except _StartupDeclined:
                self._kill(at_update_end=True)
                return
            clock = self._phase_clock
            if clock is None:
                return self._advance_exceptional(step, 1.) if self._exceptional_clock else self._advance_zero(step, 1.)
            previous = self._position
            position = clock.advance_step(step, self._backwards)
        else:
            previous = self._position
            position = clock.advance(delta, self._time_scale, self._backwards)
        if position is None:
            self._position = clock.time
            return
        if self._seek(position, previous, True, advancing=True, retire_on_error=True) is False:
            return
        if not self._active or self._position != position:
            return
        clock = self._phase_clock
        if self._backwards and clock.position == 0 and clock.completed_loops == 0:
            self.pause()
        elif not self._backwards and self.is_complete():
            self._kill(at_update_end=True) if self.auto_kill else self.pause()

    def _consume_delay(self, previous, delta, scale):
        if self._delay and 0 <= previous <= self._delay and (previous < self._delay or not self._started):
            requested = _advance_tween_clock(previous, delta, scale, self._backwards, inf)
            if requested <= self._delay:
                self._position = requested
                return False
            self._position = self._delay
        return True

    def _advance_zero(self, delta, scale=None):
        if not self._active or not self.playing:
            return
        self._locked = True
        scale = self._time_scale if scale is None else scale
        step = _f32(delta * scale)
        if -_MIN_FRAME_STEP < step < _MIN_FRAME_STEP:
            return
        previous = self._position
        if not self._consume_delay(previous, delta, scale):
            return
        if not self._initialized:
            try:
                self._ensure_initialized()
            except _StartupDeclined:
                self._kill(at_update_end=True)
                return
        position = _advance_tween_clock(previous, delta, scale, self._backwards, self.full_duration,
                                        self._backwards or previous >= 0)
        if position < self._delay and 0 <= previous < self._delay:
            self._position = position
            return
        zero_loops = (self._loops if self._loops != -1 else self._zero_completed_loops + 1)
        if self._duration == 0:
            position = self._delay
        if self._seek(position, previous, True, zero_loops=zero_loops, retire_on_error=True) is False:
            return
        if not self._active or self._position != position:
            return
        if self._duration == 0:
            if self.is_complete() and self.auto_kill:
                self._kill(at_update_end=True)
            elif self.is_complete() and not self._backwards:
                self.pause()
        elif self._backwards and position == 0:
            self.pause()
        elif not self._backwards and position >= self.full_duration:
            self._kill(at_update_end=True) if self.auto_kill else self.pause()

    def _apply(self, progress, cycle, previous, callbacks):
        raise NotImplementedError

    def _advance_exceptional(self, delta, scale=None):
        if not self._active or not self.playing:
            return
        self._locked = True
        scale = self._time_scale if scale is None else scale
        step = _f32(delta * scale)
        if -_MIN_FRAME_STEP < step < _MIN_FRAME_STEP:
            return
        previous = self._position
        if not self._consume_delay(previous, delta, scale):
            return
        if not self._initialized:
            try:
                self._ensure_initialized()
            except _StartupDeclined:
                self._kill(at_update_end=True)
                return
        requested = _advance_tween_clock(previous, delta, scale, self._backwards, inf)
        if requested < self._delay and previous < self._delay:
            self._position = requested
            return
        position, loops = _advance_exceptional_tween_clock(requested - self._delay, self._duration, self._loops)
        position += self._delay
        if self._seek(position, previous, True, zero_loops=loops, retire_on_error=True) is False:
            return
        if self._active and self.is_complete():
            self._kill(at_update_end=True) if self.auto_kill else self.pause()

    def _condition(self, kind, value=0):
        check = {
            "complete": self.is_complete, "kill": lambda: False, "start": lambda: self._started,
            "rewind": lambda: self._started and self._position <= self._delay,
            "loops": lambda: self.completed_loops() >= value, "position": lambda: self.elapsed() >= value,
        }[kind]
        return lambda: not self._active or check()

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

    def wait_for_completion(self, return_custom_yield_instruction=False):
        return WaitForCompletion(self) if return_custom_yield_instruction else self._wait("complete")

    def wait_for_kill(self, return_custom_yield_instruction=False):
        return WaitForKill(self) if return_custom_yield_instruction else self._wait("kill")

    def wait_for_start(self, return_custom_yield_instruction=False):
        return WaitForStart(self) if return_custom_yield_instruction else self._wait("start")

    def wait_for_rewind(self, return_custom_yield_instruction=False):
        return WaitForRewind(self) if return_custom_yield_instruction else self._wait("rewind")

    def wait_for_elapsed_loops(self, elapsed_loops, return_custom_yield_instruction=False):
        return WaitForElapsedLoops(self, elapsed_loops) if return_custom_yield_instruction else self._wait("loops", elapsed_loops)

    def wait_for_position(self, position, return_custom_yield_instruction=False):
        return WaitForPosition(self, position) if return_custom_yield_instruction else self._wait("position", position)
    def async_wait_for_completion(self): return self._async_wait("complete")
    def async_wait_for_kill(self): return self._async_wait("kill")
    def async_wait_for_start(self): return self._async_wait("start")
    def async_wait_for_rewind(self): return self._async_wait("rewind")
    def async_wait_for_elapsed_loops(self, elapsed_loops): return self._async_wait("loops", elapsed_loops)
    def async_wait_for_position(self, position): return self._async_wait("position", position)


class Tweener(Tween):
    _core_plugin_kind = None
    _from_value_keyword = 'from_value'
    _native_bind_name = 'bind'
    _native_interpolate_name = 'interpolate'

    @staticmethod
    def _copy_argument(value):
        return value

    def __init__(self, getter, setter, end_value, duration):
        self._numeric_value = self._numeric_job = self._sample_numeric = None
        self._sample_numeric_nested = None
        self._interpolate_numeric = None
        self._numeric_rounding = False
        self._integer_bits = 0
        super().__init__(duration)
        self._getter, self._setter = getter, setter
        self._end = end_value
        self._start = None
        self._relative = False
        self._from = False
        self._from_relative = False
        self._reset_relative_on_from_startup = False
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

    def _ensure_initialized(self):
        if not self._initialized:
            if self._start is None:
                self._initialize()
            else:
                # Immediate From captures endpoints before startup. Options may
                # still change before the plugin builds its change value.
                self._set_values(self._start, self._end)
            if self._speed_based:
                self._duration = _f32(self._speed_duration(self._duration))
                self._bind_numeric_sampler()
        return super()._ensure_initialized()

    @overload
    def from_(self): ...
    @overload
    def from_(self, is_relative: bool): ...
    @overload
    def from_(self, set_immediately: bool, is_relative: bool): ...
    @overload
    def from_(self, from_value: object, set_immediately: bool=True, is_relative: bool=False): ...
    @overload
    def from_(self, *, from_value_degrees: float, set_immediately: bool=True, is_relative: bool=False): ...
    @overload
    def from_(self, *, from_alpha_value: float, set_immediately: bool=True, is_relative: bool=False): ...
    def from_(self, *args, **kwargs):
        if not self._configure():
            return self
        value_name = self._from_value_keyword
        if value_name not in kwargs:
            value_name = 'from_value'
        from_value = kwargs.pop(value_name, _UNSET)
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
        if from_value is not _UNSET:
            from_value = self._copy_argument(from_value)
        return self._apply_from(from_value, set_immediately, relative)

    def _apply_from(self, from_value, set_immediately, relative):
        self._from, self._from_relative = True, relative
        # Eager From keeps a prior SetRelative flag. Deferred
        # implicit From temporarily stores its own relative flag, then clears
        # it at startup. These are two different operations and must not be
        # collapsed into one bit.
        self._reset_relative_on_from_startup = not set_immediately and from_value is _UNSET
        if self._reset_relative_on_from_startup:
            self._relative = relative
        self._from_value = from_value
        self._start = None
        if set_immediately or from_value is not _UNSET:
            self._initialize()
        if set_immediately:
            if self._euler:
                from infernux.lib import quatf
                self._setter(quatf.euler(*self._start))
            else:
                value = self._from_output(from_value)
                self._setter(self._snap(value, all_channels=True) if self._snapping else value)
        return self

    def _from_output(self, from_value):
        value = self._start
        if self._constraint or self._alpha_only:
            current = self._from_current if from_value is _UNSET else self._getter()
            channels = [item if (i == 3 if self._alpha_only else self._constraint & (2 << i))
                        else current[i] for i, item in enumerate(value)]
            value = self._value_type(channels) if self._sequence_value else self._value_type(*channels)
        return value

    def _relative_value(self, current, value):
        if self._alpha_only:
            return type(current)((*current[:3], current[3] + value[3]))
        return type(current)(a+b for a, b in zip(current, value, strict=True)) if isinstance(current, (tuple, list)) else current+value

    def _convert_start_value(self, value):
        return value

    def _read_startup_value(self):
        if self._manual_start is not _UNSET:
            return self._manual_start
        return self._getter()

    def _capture_values(self):
        current, end = self._read_startup_value(), self._end
        self._core_input_type = type(current)
        if self._from:
            self._from_current = current
        from infernux.lib import Vector3, quatf
        if isinstance(current, quatf) and isinstance(end, Vector3):
            from .rotation import RotateMode, _select_euler
            _select_euler(self)
            self._euler = True
            if self._vector_option_kind in ('axis', 'snapping'):
                raise TypeError("quaternion Euler options accept use_shortest360_route")
            if self._vector_option is not _UNSET:
                self._use_shortest360_route, self._snapping = self._vector_option, False
            if self._rotate_mode is None:
                self._rotate_mode = RotateMode.FAST if self._use_shortest360_route else RotateMode.FAST_BEYOND360
            if self._from and self._from_value is _UNSET and self._rotate_mode in (RotateMode.WORLD_AXIS_ADD, RotateMode.LOCAL_AXIS_ADD):
                delta = quatf.euler(*end)
                first = delta * current if self._rotate_mode == RotateMode.WORLD_AXIS_ADD else current * delta
                self._integer = self._sequence_value = False
                self._value_type = Vector3
                return first.euler_angles, -end
            current = current.euler_angles
        elif self._vector_option_kind == 'euler':
            raise TypeError("use_shortest360_route requires a quaternion getter")
        self._integer = type(current) is int and type(end) is int
        if self._integer and not self._integer_bits:
            self._integer_bits = 32 if -(2**31) <= current < 2**31 and -(2**31) <= end < 2**31 else 64
        self._sequence_value = isinstance(current, (tuple, list))
        self._value_type = type(current)
        self._normalize_constraint(current)
        start = self._convert_start_value(current) if self._manual_start is _UNSET else self._manual_start
        if self._from:
            if type(self._from_value) in (int, float):
                if isinstance(current, Vector3):
                    self._from_value = Vector3(self._from_value, self._from_value, self._from_value)
                elif isinstance(current, list) and len(current) == 4:
                    self._alpha_only = True
                    self._from_value = [*current[:3], self._from_value]
            if self._from_value is _UNSET:
                start, end = end, start
                if self._euler and self._rotate_mode == RotateMode.FAST_BEYOND360:
                    start = start + end
            else:
                start = self._from_value
            if self._from_relative:
                start = self._relative_value(current, start)
                if self._from_value is not _UNSET:
                    end = self._relative_value(current, end)
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
        self._delta = self._calculate_delta(start, end)
        self._compile_numeric_value()

    def _calculate_delta(self, start, end):
        if self._euler:
            from .rotation import _euler_tween_change
            return _euler_tween_change(start, end, self._rotate_mode.value, self._relative)
        return tuple(b - a for a, b in zip(start, end)) if self._sequence_value else end - start

    def _compile_numeric_value(self):
        if self._euler:
            from .rotation import _compile_euler
            return _compile_euler(self)
        self._numeric_rounding = False
        if not self._sequence_value and not self._euler and isinstance(self._start, (int, float)):
            self._numeric_value = _ScalarTweenSnapshot(self._start, self._delta)
        elif not self._euler and (snapshot := _VECTOR_SNAPSHOTS.get(type(self._start))) is not None:
            self._numeric_value = snapshot(self._start, self._delta, self._snapping)
            self._numeric_rounding = self._snapping
        else:
            self._numeric_value = None
        self._bind_numeric_sampler()

    def _bind_numeric_sampler(self):
        self._interpolate_numeric = (getattr(self._numeric_value, self._native_interpolate_name)
                                     if self._numeric_value is not None else None)
        if self._numeric_value is not None and self._numeric_ease is not None:
            self._numeric_job = getattr(self._numeric_value, self._native_bind_name)(self._numeric_ease, self._duration)
            self._sample_numeric = self._numeric_job.__call__
            self._sample_numeric_nested = self._numeric_job.sample_nested
        else:
            self._numeric_job = self._sample_numeric = None
            self._sample_numeric_nested = None
            if self._numeric_value is not None and self._core_plugin_kind in ('vector', 'color', 'euler'):
                self._sample_numeric = partial(self._numeric_value.sample_custom, self._ease)
                self._sample_numeric_nested = self._sample_numeric
            elif self._numeric_value is not None and self._core_plugin_kind in ('scalar', 'unsigned'):
                arguments = getattr(self._ease, '_time_arguments', None)
                name = 'sample_custom' if arguments is None else 'sample_custom_time'
                method = self._native_interpolate_name.replace('interpolate', name)
                self._sample_numeric = partial(getattr(self._numeric_value, method),
                                               self._ease if arguments is None else arguments)
                self._sample_numeric_nested = self._sample_numeric

    def _sample_parent_incremental(self, progress, own, parent):
        offset = parent._incremental_cycles(0, False)
        multiplier = self._loops if self.loop_type == LoopType.INCREMENTAL else 1
        if self._sample_numeric_nested is not None:
            return self._sample_numeric_nested(progress, own, multiplier, offset)
        return self._interpolate_numeric(self._ease(progress), own, multiplier, offset)

    def _initialize(self):
        if self._start is None:
            start, end = self._capture_values()
            if self._from and self._reset_relative_on_from_startup:
                self._relative = False
            if self._relative:
                end = self._relative_value(start, end)
            self._set_values(start, end)

    def _distance(self):
        if self._alpha_only:
            return abs(self._delta[3])
        if self._constraint:
            return sqrt(sum(float(value)**2 for index, value in enumerate(self._delta) if self._constraint & (2 << index)))
        return sqrt(sum(float(item)**2 for item in self._delta)) if self._sequence_value or hasattr(self._delta, "__iter__") else abs(self._delta)

    def _speed_duration(self, units):
        if self._euler:
            from infernux.lib._Infernux import _euler_tween_speed
            return _euler_tween_speed(self._delta, units)
        return self._distance() / units

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
        if not self._active or self._parent is not None:
            return self
        duration = _f32(duration)
        if start is not _UNSET:
            start = self._copy_argument(start)
        if end is not _UNSET:
            end = self._copy_argument(end)
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
            self._duration = _f32(self._speed_duration(duration)) if self._speed_based and self._initialized else duration
            self._bind_numeric_sampler()
        self._ensure_initialized()
        self._seek_serial += 1
        if self._seek(min(self._position, self._delay), self._position, False, notify_update=False) is False:
            return self
        if self._backwards:
            self.pause()
        return self

    def _apply(self, progress, cycle, previous, callbacks):
        if self._euler:
            from .rotation import _apply_euler
            return _apply_euler(self, progress, cycle, previous, callbacks)
        setter, integer = self._setter, self._integer
        constraint, alpha_only, snapping = self._constraint, self._alpha_only, self._snapping
        numeric_rounding = self._numeric_rounding if snapping else False
        if constraint or alpha_only or (snapping and not numeric_rounding):
            value_type, sequence_value = self._value_type, self._sequence_value
        if constraint or alpha_only:
            getter = self._getter
        if self._numeric_value is not None:
            incremental = self._incremental_cycles(cycle, False) if self.loop_type == LoopType.INCREMENTAL else 0
            parent = self._parent
            if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
                value = self._sample_parent_incremental(progress, incremental, parent)
            elif self._sample_numeric is not None:
                value = self._sample_numeric(progress, incremental)
            else:
                value = self._interpolate_numeric(self._ease(progress), incremental)
        else:
            incremental = self._incremental_cycles(cycle)
            start, delta = self._start, self._delta
            value_type, sequence_value = self._value_type, self._sequence_value
            ease = self._ease(progress)
            factor = ease + incremental
            if sequence_value:
                value = value_type([a + d * factor for a, d in zip(start, delta)])
            else:
                value = start + delta * factor
        if integer:
            value = round(value)
        else:
            if constraint or alpha_only:
                current = getter()
                components = [item if (index == 3 if alpha_only else constraint & (2 << index))
                              else current[index] for index, item in enumerate(value)]
                value = value_type(components) if sequence_value else type(value)(*components)
            if snapping and not numeric_rounding:
                value = _snap_value(value, integer, constraint, value_type, sequence_value)
        setter(value)

    def _normalize_constraint(self, value):
        # Vector plugins select one exact axis. Combinations and axes outside
        # the value's dimension use the unconstrained interpolation route.
        if self._constraint and not self._euler:
            dimensions = value.shape[-1] if hasattr(value, 'shape') else len(tuple(value))
            if self._constraint not in tuple(2 << i for i in range(dimensions)):
                self._constraint = AxisConstraint.NONE

    def _snap(self, value, *, all_channels=False):
        return _snap_value(value, self._integer, self._constraint, self._value_type,
                           self._sequence_value, all_channels)


class TweenerCore(Tweener):
    """Typed tween storage shared by built-in and user-defined plugins.

    Direct field writes retain their meaning: changing an endpoint does not
    recalculate change_value. Use change_values() to recapture the transition.
    Replacing fields rebinds native storage; in-place vector edits are read
    directly by the prepared job, without Python polling during playback.
    """

    def get_plugin(self):
        from ._builtin_plugins import get_builtin_plugin
        if self._core_plugin_kind == 'vector' and type(self._end) is Vector3 and '_core_input_type' not in self.__dict__:
            from infernux.lib import quatf
            declared = getattr(self._getter, '__annotations__', {}).get('return')
            self._core_input_type = declared if declared in (quatf, Vector3) else type(self._getter())
            if self._core_input_type is quatf:
                from .rotation import _select_euler
                _select_euler(self)
        return get_builtin_plugin(self)

    def _storage_default(self):
        end = self._end
        if isinstance(end, (tuple, list)):
            return type(end)(0.0 for _ in end)
        return type(end)()

    @property
    def start_value(self):
        if self._initialized or self._start is not None:
            return self._start
        value = self.__dict__.get('_pending_start_value', _UNSET)
        return self._storage_default() if value is _UNSET else value

    @start_value.setter
    def start_value(self, value):
        if self._initialized or self._start is not None:
            self._start = value
            if self._initialized:
                self._refresh_core_value()
        else:
            self._pending_start_value = value

    @property
    def end_value(self):
        return self._end

    @end_value.setter
    def end_value(self, value):
        self._end = value
        if self._core_plugin_kind == 'euler' and self._dynamic and self._initialized:
            self._compile_numeric_value()

    @property
    def change_value(self):
        if self._initialized:
            return self._delta
        value = self.__dict__.get('_pending_change_value', _UNSET)
        return self._storage_default() if value is _UNSET else value

    @change_value.setter
    def change_value(self, value):
        if self._initialized:
            self._delta = value
            self._refresh_core_value()
        else:
            self._pending_change_value = value

    @property
    def getter(self):
        return self._getter

    @getter.setter
    def getter(self, value):
        self._getter = value

    @property
    def setter(self):
        return self._setter

    @setter.setter
    def setter(self, value):
        self._setter = value

    @property
    def plug_options(self):
        options = self.__dict__.get('_core_options')
        if options is None:
            options = self.get_plugin().options_type()
            options._owner = self
            self._core_options = options
        return options

    @plug_options.setter
    def plug_options(self, value):
        options_type = self.get_plugin().options_type
        if not isinstance(value, options_type):
            raise TypeError("plug_options must have the plugin's declared options type")
        from copy import copy
        options = copy(value)
        self._detach_core_options()
        for field, storage in options._fields:
            setattr(self, storage, getattr(options, field))
        options._owner = self
        self._core_options = options
        if options._fields and self._initialized:
            self._core_options_changed()

    def _detach_core_options(self):
        options = self.__dict__.pop('_core_options', None)
        if options is not None:
            for field, _ in options._fields:
                options._values[field] = getattr(options, field)
            options._owner = None
        return options

    def _on_despawn(self):
        super()._on_despawn()
        options = self._detach_core_options()
        if options is not None:
            options.reset()

    def _refresh_core_value(self):
        self._compile_numeric_value()

    def _core_options_changed(self):
        self._refresh_core_value()

    def _core_option_changed(self, storage):
        if self._core_plugin_kind == 'euler':
            if self._initialized:
                self._compile_numeric_value()
            return
        if storage == '_constraint' and self._start is not None:
            self._normalize_constraint(self._start)
        elif (storage == '_snapping' and self._numeric_value is not None
              and (self._core_plugin_kind == 'vector' or self._numeric_rounding)):
            self._refresh_core_value()


class _FloatTweener(TweenerCore):
    _core_plugin_kind = 'scalar'
    _scalar_type = float
    _scalar_bits = 0

    def _refresh_core_value(self):
        if self._integer:
            # Direct start/change writes must not overwrite the independent
            # public end field or derive a new change from it.
            self._numeric_value = _SignedIntegerTweenSnapshot(
                self._start, self._start + self._delta, self._integer_bits)
            self._bind_numeric_sampler()
        else:
            self._compile_numeric_value()

    def _compile_numeric_value(self):
        if self._integer:
            self._numeric_value = _SignedIntegerTweenSnapshot(self._start, self._end, self._integer_bits)
            self._start, self._end, self._delta = (self._numeric_value.start_value,
                                                  self._numeric_value.end_value,
                                                  self._numeric_value.change_value)
        else:
            self._numeric_value = _ScalarTweenSnapshot(self._start, self._delta, self._snapping)
            self._numeric_rounding = True
        self._bind_numeric_sampler()

    def _apply(self, progress, cycle, previous, callbacks):
        setter = self._setter
        incremental = self._incremental_cycles(cycle, False) if self.loop_type == LoopType.INCREMENTAL else 0
        parent = self._parent
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            value = self._sample_parent_incremental(progress, incremental, parent)
        elif self._sample_numeric is not None:
            value = self._sample_numeric(progress, incremental)
        else:
            value = self._interpolate_numeric(self._ease(progress), incremental)
        setter(value)

    def set_options(self, snapping: bool):
        if not self._active:
            return self
        if type(snapping) is not bool:
            raise TypeError("snapping must be bool")
        self._snapping = snapping
        if self._numeric_value is not None:
            self._refresh_core_value()
        return self


class _ColorTweener(TweenerCore):
    _core_plugin_kind = 'color'
    _from_value_keyword = 'from_alpha_value'

    def __init__(self, getter, setter, end_value, duration):
        super().__init__(getter, setter, _ColorValue(end_value), duration)

    @staticmethod
    def _copy_argument(value):
        return _ColorValue(value) if isinstance(value, (tuple, list)) else value

    def _read_startup_value(self):
        if self._from and not self._from_relative and isinstance(self._from_value, (tuple, list)):
            return list(self._from_value)
        return list(super()._read_startup_value())

    def _compile_numeric_value(self):
        self._start, self._delta = _color_value(self._start), _color_value(self._delta)
        self._numeric_value = (_LiveColorTweenSnapshot(self._start._native, self._delta._native)
                               if self._value_type is list else None)
        self._bind_numeric_sampler()

    def _set_values(self, start, end):
        self._start, self._end = _ColorValue(start), _ColorValue(end)
        self._delta = self._calculate_delta(self._start, self._end)
        self._compile_numeric_value()

    def _from_output(self, from_value):
        return list(super()._from_output(from_value))

    def _apply(self, progress, cycle, previous, callbacks):
        if self._numeric_value is None:
            return super()._apply(progress, cycle, previous, callbacks)
        # Color has one option; keep unrelated scalar/vector options out of
        # its hot path while capturing delegates before user easing/getters.
        setter, alpha_only = self._setter, self._alpha_only
        if alpha_only:
            getter = self._getter
        own = self._incremental_cycles(cycle, False) if self.loop_type == LoopType.INCREMENTAL else 0
        parent = self._parent
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            value = self._sample_parent_incremental(progress, own, parent)
        elif self._sample_numeric is not None:
            value = self._sample_numeric(progress, own)
        else:
            value = self._interpolate_numeric(self._ease(progress), own)
        if alpha_only:
            value[:3] = getter()[:3]
        setter(value)

    @TweenerCore.start_value.setter
    def start_value(self, value):
        TweenerCore.start_value.fset(self, _ColorValue(value))

    @TweenerCore.end_value.setter
    def end_value(self, value):
        TweenerCore.end_value.fset(self, _ColorValue(value))

    @TweenerCore.change_value.setter
    def change_value(self, value):
        TweenerCore.change_value.fset(self, _ColorValue(value))

    def _distance(self):
        return 1.0  # Color speed is a normalized transition per second.

    def set_options(self, alpha_only: bool):
        if not self._active:
            return self
        if type(alpha_only) is not bool:
            raise TypeError("alpha_only must be bool")
        self._alpha_only = alpha_only
        return self


class _VectorTweener(TweenerCore):
    _core_plugin_kind = 'vector'
    _copy_argument = staticmethod(_copy_vector)

    def __init__(self, getter, setter, end_value, duration):
        super().__init__(getter, setter, _copy_vector(end_value), duration)

    def _read_startup_value(self):
        if self._core_plugin_kind == 'euler':
            return self._getter()
        if type(self._end) is Vector3:
            # An untyped Vector3 endpoint also accepts a quaternion getter.
            # Only a declared vector contract can skip that discovery read.
            kind = self.__dict__.get('_core_input_type')
            if kind is None:
                kind = getattr(self._getter, '__annotations__', {}).get('return')
            if kind is not Vector3 and kind not in ('Vector3', 'infernux.lib.Vector3'):
                return self._getter()
        if self._from and not self._from_relative and type(self._from_value) is type(self._end):
            return self._from_value
        return super()._read_startup_value()

    def _apply(self, progress, cycle, previous, callbacks):
        if self._euler:
            from .rotation import _apply_euler
            return _apply_euler(self, progress, cycle, previous, callbacks)
        if self._numeric_value is None:
            return super()._apply(progress, cycle, previous, callbacks)
        setter, constraint = self._setter, self._constraint
        if constraint:
            getter = self._getter
        own = self._incremental_cycles(cycle, False) if self.loop_type == LoopType.INCREMENTAL else 0
        parent = self._parent
        if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
            value = self._sample_parent_incremental(progress, own, parent)
        elif self._sample_numeric is not None:
            value = self._sample_numeric(progress, own)
        else:
            value = self._interpolate_numeric(self._ease(progress), own)
        if constraint:
            current = getter()
            components = [item if constraint & (2 << i) else current[i] for i, item in enumerate(value)]
            value = type(value)(*components)
        setter(value)

    def _set_values(self, start, end):
        super()._set_values(_copy_vector(start), _copy_vector(end))

    def _from_output(self, from_value):
        return _copy_vector(super()._from_output(from_value))

    @TweenerCore.start_value.setter
    def start_value(self, value):
        TweenerCore.start_value.fset(self, _copy_vector(value))

    @TweenerCore.end_value.setter
    def end_value(self, value):
        TweenerCore.end_value.fset(self, _copy_vector(value))

    @TweenerCore.change_value.setter
    def change_value(self, value):
        TweenerCore.change_value.fset(self, _copy_vector(value))

    def _calculate_delta(self, start, end):
        delta = super()._calculate_delta(start, end)
        if self._constraint and not self._euler:
            # The vector plugin captures only its selected change channel at
            # startup. A later option switch must not recapture other deltas.
            delta = type(delta)(*(value if self._constraint & (2 << i) else 0
                                 for i, value in enumerate(delta)))
        return delta

    @overload
    def set_options(self, snapping: bool): ...
    @overload
    def set_options(self, axis_constraint: AxisConstraint, snapping: bool=False): ...
    @overload
    def set_options(self, use_shortest360_route: bool=True): ...
    def set_options(self, *args, **kwargs):
        if not self._active:
            return self
        previous_snapping = self._snapping
        if 'use_shortest360_route' in kwargs or not args and not kwargs:
            if args or len(kwargs) > 1:
                raise TypeError("invalid quaternion options overload")
            option = kwargs.get('use_shortest360_route', True)
            if type(option) is not bool:
                raise TypeError("use_shortest360_route must be bool")
            self._vector_option, self._vector_option_kind = option, 'euler'
            if self._start is not None or self._core_plugin_kind == 'euler':
                if not self._euler and self._core_plugin_kind != 'euler':
                    raise TypeError("use_shortest360_route requires a quaternion getter")
                self._use_shortest360_route, self._snapping = option, False
                from .rotation import RotateMode
                self._rotate_mode = RotateMode.FAST if option else RotateMode.FAST_BEYOND360
                if self._start is not None and not self._initialized:
                    self._set_values(self._start, self._end)
                elif self._initialized:
                    self._compile_numeric_value()
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
        if constraint is not _UNSET:
            self._constraint = constraint
        self._snapping = False if snapping is _UNSET else snapping
        if not isinstance(self._constraint, AxisConstraint) or type(self._snapping) is not bool:
            raise TypeError("vector options need AxisConstraint and bool")
        if self._start is not None:
            self._normalize_constraint(self._start)
        if (self._euler or self._core_plugin_kind == 'euler') and self._vector_option is not _UNSET:
            self._use_shortest360_route, self._snapping = self._vector_option, False
            from .rotation import RotateMode
            self._rotate_mode = RotateMode.FAST if self._vector_option else RotateMode.FAST_BEYOND360
            if self._start is not None and not self._initialized:
                self._set_values(self._start, self._end)
            elif self._initialized:
                self._compile_numeric_value()
        elif self._numeric_value is not None and self._snapping != previous_snapping:
            self._compile_numeric_value()
        return self


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
        self._assign_ease(resolve_ease(Ease.LINEAR, duration=lambda: self._duration))
        self._sample_context = None
        self._failed_children = set()

    def set_delay(self, delay, as_prepended_interval_if_sequence=True):
        return self.prepend_interval(delay) if as_prepended_interval_if_sequence else super().set_delay(delay)

    def _ensure_initialized(self):
        if (not self._initialized and not self._entries
                and not any(callback is not None for name, callback in self._callbacks.items() if name != 'waypoint')):
            raise _StartupDeclined()
        if not self._initialized and self._relative:
            for _, item in self._entries:
                if isinstance(item, Tween):
                    item._set_relative(True)
        if not self._initialized and self._inverted:
            # Inverted roots capture and apply their leaf endpoints at startup.
            # This is initialization, not public completion or a timeline visit.
            for _, item in self._entries:
                if isinstance(item, Tween) and not isinstance(item, Sequence):
                    item._ensure_initialized()
                    item._set_clock_position(item.full_duration)
                    cycle, progress = item._progress_at(item._position)
                    item._apply(progress, cycle, 0.0, False)
            self._last_progress = 1.0
            self._last_sample = self._ease(1.0) * self._duration
        return super()._ensure_initialized()

    def set_speed_based(self, is_speed_based=True):
        return self

    def _set_relative(self, relative):
        self._relative = relative

    def insert(self, at_position, t):
        if not self._configure():
            return self
        at_position = _f32(at_position)
        if at_position < 0 or not isfinite(at_position):
            raise ValueError("Insertion time must be finite and nonnegative")
        if t is self or t._parent is not None or t._started or not t._active:
            raise ValueError("A sequence owns a live, unstarted tween exactly once")
        if t._loops == -1:
            t._loops = 2**31 - 1
        # Child delay becomes timeline space, rather than a delay that is
        # repeated or considered by subsequent Join calls. A nested child's
        # lifetime belongs to the sequence, including at completion.
        at_position = _f32(at_position + t._delay)
        t._delay = 0.0
        t._refresh_full_duration()
        t.auto_kill = False
        t._speed_based = False
        if t._owner is not None:
            t._owner._remove(t)
        if t._link is not None:
            t._link.detach(t)
        t._parent = self
        self._entries.append((float(at_position), t))
        self._entries.sort(key=lambda entry: entry[0])
        self._duration = max(self._duration, _f32(at_position + t.full_duration))
        self._refresh_full_duration()
        self._last_insert = at_position
        return self

    def append(self, t): return self.insert(self._duration, t)
    def join(self, t): return self.insert(self._last_insert, t)

    def append_interval(self, interval):
        if not self._configure():
            return self
        interval = _f32(interval)
        if not isfinite(interval) or interval < 0:
            raise ValueError("Interval must be finite and nonnegative")
        self._last_insert = self._duration
        self._duration = _f32(self._duration + interval)
        self._refresh_full_duration()
        return self

    def prepend_interval(self, interval):
        if not self._configure():
            return self
        interval = _f32(interval)
        if not isfinite(interval) or interval < 0:
            raise ValueError("Interval must be finite and nonnegative")
        self._duration = _f32(self._duration + interval)
        self._refresh_full_duration()
        self._entries = [(_f32(time + interval), item) for time, item in self._entries]
        self._last_insert = _f32(self._last_insert + interval)
        return self

    def prepend(self, t):
        if not self._configure():
            return self
        if t is self or t._parent is not None or t._started or not t._active:
            raise ValueError("A sequence owns a live, unstarted tween exactly once")
        if t._loops == -1:
            t._loops = 2**31 - 1
            t._refresh_full_duration()
        duration = t.full_duration
        self.prepend_interval(duration)
        return self.insert(0.0, t)

    def insert_callback(self, at_position, callback):
        if not self._configure():
            return self
        at_position = _f32(at_position)
        if not isfinite(at_position) or at_position < 0:
            raise ValueError("Callback time must be finite and nonnegative")
        self._entries.append((float(at_position), callback))
        self._entries.sort(key=lambda entry: entry[0])
        self._duration = max(self._duration, at_position)
        self._refresh_full_duration()
        self._last_insert = at_position
        return self

    def append_callback(self, callback): return self.insert_callback(self._duration, callback)
    def prepend_callback(self, callback): return self.insert_callback(0.0, callback)
    def join_callback(self, callback): return self.insert_callback(self._last_insert, callback)

    def _apply(self, progress, cycle, previous, callbacks):
        if self._sample_context is not None:
            # A reentrant control starts at the sample whose child callback
            # is running, rather than the previous completed traversal.
            active_cycle, _, active_progress, active_sample = self._sample_context
            self._last_sample = active_sample
            self._last_progress = active_progress
            self._sample_cycle, self._sampled = active_cycle, True
        if not self._duration:
            completed_steps = 0
        elif callbacks:
            completed_steps = self._completed_steps(previous, self._is_complete_at(previous), self._backwards)
        else:
            completed_steps = abs(self.completed_loops() - self._completed_loops_at(previous))
        inverse = (self.loop_type == LoopType.YOYO and cycle % 2 != 0) != self._inverted
        previous_inverse = ((self.loop_type == LoopType.YOYO and self.has_loops
                             and self._progress_at(previous)[0] % 2 != 0) != self._backwards) != self._inverted
        if self.loop_type == LoopType.YOYO and self.has_loops:
            turns = cycle - self._sample_cycle + completed_steps if not callbacks else (
                cycle - self._sample_cycle if not completed_steps else 0)
            if turns % 2 and (not callbacks or completed_steps):
                # Express the previous timeline clock in the current phase.
                self._last_sample = self._duration - self._last_sample
                self._last_progress = 1 - self._last_progress
        if callbacks and completed_steps > 0:
            first_cycle = self._sample_cycle
            old_sample, old_progress = self._last_sample, self._last_progress
            for index in range(completed_steps):
                completed = first_cycle - index if self._backwards else first_cycle + index
                endpoint = 0.0 if self.loop_type == LoopType.YOYO and completed % 2 else 1.0
                if self._backwards:
                    endpoint = 1 - endpoint
                if self._inverted:
                    endpoint = 1-endpoint
                if not self._sample_children(endpoint, completed, True, inverse, previous_inverse):
                    return False
                if self.loop_type == LoopType.YOYO and self.has_loops:
                    previous_inverse = not previous_inverse
            if completed_steps == 1 and self.is_complete():
                return True
            if self.is_complete():
                if self.loop_type == LoopType.YOYO and (cycle - first_cycle) % 2:
                    old_sample, old_progress = self._duration - old_sample, 1 - old_progress
                self._last_sample, self._last_progress = old_sample, old_progress
            elif self.loop_type == LoopType.RESTART and self._last_sample > 0:
                self._sample_children(1.0 if self._inverted else 0.0, cycle, False, inverse, previous_inverse)
                self._sampled = False
            elif self.loop_type == LoopType.INCREMENTAL:
                self._last_sample = self._duration if self._inverted else 0.0
                self._last_progress = 1.0 if self._inverted else 0.0
                self._sampled = False
            elif self.loop_type == LoopType.YOYO:
                inverse = (cycle % 2 != 0) != self._inverted
                self._last_sample = self._duration if inverse else 0.0
                self._last_progress = 1.0 if inverse else 0.0
        return self._sample_children(progress, cycle, callbacks, inverse, previous_inverse)

    def _assign_ease(self, sampler):
        super()._assign_ease(sampler)
        self._ease_at = (self._linear_clock_at if self._numeric_ease is not None and self._numeric_ease.is_linear
                         else self._eased_clock_at)

    @staticmethod
    def _linear_clock_at(progress, cycle):
        return progress

    def _eased_clock_at(self, progress, cycle):
        # Sequence eases its forward clock before reversing the timeline.
        # A value tweener instead eases the reversed clock inside its plugin.
        inverse = (self.loop_type == LoopType.YOYO and cycle % 2 != 0) != self._inverted
        return 1 - self._ease(1 - progress) if inverse else self._ease(progress)

    def _sample_children(self, progress, cycle, callbacks, inverse, previous_inverse):
        previous_context = self._sample_context
        self._sample_context = (cycle, self._last_progress, progress, self._last_sample)
        try:
            return self._sample_items(progress, cycle, callbacks, inverse, previous_inverse)
        finally:
            self._sample_context = previous_context
            if previous_context is None and self._failed_children:
                failed, self._failed_children = self._failed_children, set()
                retired = {item for item, _, _ in failed}
                self._entries[:] = [(start, item) for start, item in self._entries if item not in retired]
                for item, generation, owner in failed:
                    if not item._active and item._generation == generation:
                        item._parent = None
                        owner._recycle(item)

    def _sample_items(self, progress, cycle, callbacks, inverse, previous_inverse):
        # The reference stores its eased sequence clock as float before visiting
        # children. Retaining a double ratio/product changes public child clocks
        # and can move seeks onto the wrong side of an exact boundary.
        sample = _f32(self._ease_at(progress, cycle) * self._duration)
        old_sample = self._last_sample
        include_start = not self._sampled
        previous_context = self._sample_context
        self._sample_context = (cycle, self._last_progress, progress, sample)
        position, was_playing = self._position, self.playing
        control_root = self
        while control_root._parent is not None:
            control_root = control_root._parent
        owner_position, owner_serial, owner_generation = (
            control_root._position, control_root._seek_serial, control_root._generation)
        indices = range(len(self._entries)-1, -1, -1) if sample < old_sample else range(len(self._entries))
        try:
            for index in indices:
                if (not self._active or self._position != position or not control_root._active
                        or control_root._generation != owner_generation or control_root._seek_serial != owner_serial
                        or control_root._position != owner_position):
                    return False
                if was_playing and not self.playing:
                    break
                start, item = self._entries[index]
                if isinstance(item, Tween):
                    end = start + item.full_duration
                    if sample < old_sample:
                        if end < sample or start > old_sample or not item._initialized:
                            continue
                    elif (start > sample or (start > 0 and end <= old_sample)
                          or (start <= 0 and end < old_sample)):
                        continue
                    if item._active and (sample >= start + item._delay or old_sample >= start + item._delay):
                        try:
                            was_child_playing = item.playing
                            item.playing = False
                            item._backwards = sample < old_sample
                            # At a child's end the reference forces startup
                            # before Goto. A silent decline has already marked
                            # it initialized, so the endpoint still evaluates.
                            if not item._initialized and sample >= end:
                                try:
                                    item._ensure_initialized()
                                except _StartupDeclined:
                                    pass
                            if item._seek(min(item.full_duration, max(0, sample - start)),
                                          item._position if callbacks else min(item.full_duration, max(0, old_sample - start)), callbacks and sample >= start) is False:
                                return False
                            if was_child_playing and item._active and not item.playing:
                                if not item._emit("pause"):
                                    return False
                        except Exception as error:
                            root = self
                            while root._parent is not None:
                                root = root._parent
                            owner = root._callback_manager or _default_manager
                            if not owner.use_safe_mode and not isinstance(error, _StartupDeclined):
                                raise
                            if not isinstance(error, (_NestedTweenFailure, _EvaluationFailure, _StartupDeclined)):
                                owner._record_error(error)
                            # A lone failed child with no callbacks has nothing
                            # left to preserve. Intervals do not count as entries.
                            sole_child = len(self._entries) == 1 and not self._callbacks
                            if owner.nested_tween_failure_behaviour == NestedTweenFailureBehaviour.KILL_WHOLE_SEQUENCE or sole_child:
                                if isinstance(error, (_NestedTweenFailure, _EvaluationFailure, _StartupDeclined)):
                                    raise
                                raise _NestedTweenFailure(str(error)) from error
                            generation = item._generation
                            item._kill()
                            self._failed_children.add((item, generation, owner))
                            if not self._active:
                                return False
                elif callbacks and (previous_inverse if sample < old_sample else
                                    not previous_inverse and self._backwards == inverse) and (
                        old_sample < start <= sample or (sample < old_sample and sample <= start <= old_sample)
                        or (start == old_sample and (include_start or start == 0))):
                    if not self._invoke(item, pause_interrupts=False):
                        return False
            if control_root._seek_serial != owner_serial:
                return False
            self._last_sample, self._last_progress = sample, progress
            self._sample_cycle, self._sampled = cycle, True
            return True
        finally:
            self._sample_context = previous_context

    def _despawn(self, owner):
        super()._despawn(owner)
        for _, item in self._entries:
            if isinstance(item, Tween):
                item._retiring_owner = owner
                item._kill()
        if owner is not None:
            owner._recycle(self)


class TweenManager:
    time_scale = _single_field('_time_scale')
    unscaled_time_scale = _single_field('_unscaled_time_scale')
    max_smooth_unscaled_time = _single_field('_max_smooth_unscaled_time')
    default_ease_overshoot_or_amplitude = _single_field('_default_ease_overshoot_or_amplitude')
    default_ease_period = _single_field('_default_ease_period')

    def __init__(self, on_activity=None):
        self._settings = None
        self._initialized = False
        self.default_recyclable = False
        self.use_safe_mode = True
        self.draw_gizmos = True
        self.show_editor_report = False
        self.debug_mode = False
        self._debug_store_target_id = True
        self.nested_tween_failure_behaviour = NestedTweenFailureBehaviour.TRY_TO_PRESERVE_SEQUENCE
        self.log_behaviour = LogBehaviour.ERRORS_ONLY
        self.safe_mode_log_behaviour = SafeModeLogBehaviour.WARNING
        self.rewind_callback_mode = RewindCallbackMode.FIRE_IF_POSITION_CHANGED
        self.on_will_log = None
        self._safe_mode_errors = 0
        self._pool_by_type = {}
        self._pool_storage = {"tweeners": [None]*200, "sequences": [None]*50}
        self._pool_free = {name: list(range(len(slots))) for name, slots in self._pool_storage.items()}
        self._time_scale = 1.0
        self._unscaled_time_scale = 1.0
        self.use_smooth_delta_time = False
        self._max_smooth_unscaled_time = _f32(.15)
        self.default_update_type = UpdateType.NORMAL
        self.default_time_scale_independent = False
        self.default_auto_kill = True
        self.default_auto_play = AutoPlay.ALL
        self.default_loop_type = LoopType.RESTART
        self.default_ease_type = Ease.OUT_QUAD
        self._default_ease_overshoot_or_amplitude = _DEFAULT_EASE_ARGS[0]
        self._default_ease_period = 0.0
        self._tweens = {}
        self._active_by_phase = {phase: 0 for phase in UpdateType}
        self._next_dispatch_order = 0
        self._dispatch_contexts = []
        self._running = {phase: {} for phase in UpdateType}
        self._playing_counts = {phase: 0 for phase in UpdateType}
        self._running_snapshots = {phase: None for phase in UpdateType}
        self._on_activity = on_activity
        self._update_depth = 0
        self._pending_commits = {}
        self._pending_kills = {}
        self._active_counts = [0, 0]
        self._peak_counts = [0, 0]

    @property
    def debug_store_target_id(self):
        return self.debug_mode and self.use_safe_mode and self._debug_store_target_id

    @debug_store_target_id.setter
    def debug_store_target_id(self, value):
        self._debug_store_target_id = bool(value)

    def init(self, recycle_all_by_default=None, use_safe_mode=None, log_behaviour=None):
        if self._initialized:
            return self
        if recycle_all_by_default is not None:
            self.default_recyclable = bool(recycle_all_by_default)
        if use_safe_mode is not None:
            self.use_safe_mode = bool(use_safe_mode)
        if log_behaviour is not None:
            self.log_behaviour = LogBehaviour(log_behaviour)
        self._initialized = True
        return self

    def set_capacity(self, tweeners_capacity, sequences_capacity):
        self.set_tweens_capacity(tweeners_capacity, sequences_capacity)
        return self

    def set_tweens_capacity(self, tweeners_capacity, sequences_capacity):
        if any(type(n) is not int or n < 0 for n in (tweeners_capacity, sequences_capacity)):
            raise ValueError("capacities must be nonnegative integers")
        if self.total_active_tweens():
            raise RuntimeError("set capacity before creating active tweens")
        self._pool_storage = {"tweeners": [None]*max(tweeners_capacity, sequences_capacity),
                              "sequences": [None]*sequences_capacity}
        self.clear_cached_tweens()

    def clear_cached_tweens(self):
        self._pool_by_type.clear()
        for name, slots in self._pool_storage.items():
            slots[:] = [None]*len(slots)
            self._pool_free[name] = list(range(len(slots)))

    def total_pooled_tweens(self):
        return sum(len(slots)-len(self._pool_free[name]) for name, slots in self._pool_storage.items())

    def _new(self, kind, *args, pool_key=None):
        key = kind if pool_key is None else pool_key
        indices = self._pool_by_type.get(key)
        if not indices:
            item = kind(*args)
            item._pool_key = key
            return item
        family = "sequences" if issubclass(kind, Sequence) else "tweeners"
        index = indices.pop()
        item = self._pool_storage[family][index]
        self._pool_storage[family][index] = None
        self._pool_free[family].append(index)
        generation = item._generation
        reuse = item._pool_reuse_state() if hasattr(item, '_pool_reuse_state') else {}
        if item._callbacks.get("pause") is not None:
            reuse["_callbacks"] = {"pause": item._callbacks["pause"]}
        item.__dict__.clear()
        item.__dict__.update(reuse)
        item._generation = generation
        kind.__init__(item, *args)
        item._pool_key = key
        return item

    def _recycle(self, tween):
        if not tween.recyclable:
            return
        family = "sequences" if isinstance(tween, Sequence) else "tweeners"
        free = self._pool_free[family]
        if not free:
            return
        index = free.pop()
        # Kill callbacks and waiters have finished before entering the pool.
        tween.target = tween.id = None
        tween._retiring_owner = None
        tween._callback_manager = None
        preserved = getattr(tween, '_pool_preserved_fields', ())
        for name in ("_getter", "_setter", "_start", "_end", "_delta", "_ease", "_ease_source", "_startup_rotation_getter"):
            if name in tween.__dict__ and name not in preserved:
                tween.__dict__[name] = None
        if isinstance(tween, Sequence):
            tween._entries.clear()
        self._pool_storage[family][index] = tween
        self._pool_by_type.setdefault(getattr(tween, '_pool_key', type(tween)), []).append(index)

    def validate(self):
        invalid = 0
        def check(tween):
            getter = getattr(tween, "_getter", None)
            if callable(getter):
                getter()
            if isinstance(tween, Sequence):
                for _, item in tween._entries:
                    if isinstance(item, Tween):
                        check(item)
        for tween in self._matching():
            try:
                check(tween)
            except Exception:
                tween.kill()
                invalid += 1
        return invalid

    def add(self, tween):
        self._initialized = True
        already_owned = tween._owner is self
        if tween._owner is None:
            if not tween._recyclable_configured:
                tween.recyclable = self.default_recyclable
            if not tween._update_configured and tween.update_type == UpdateType.NORMAL:
                tween.update_type, tween.independent = self.default_update_type, self.default_time_scale_independent
            if not tween._ease_configured and not isinstance(tween, Sequence):
                ease_args = self.default_ease_overshoot_or_amplitude, self.default_ease_period
                if tween._ease_source is not self.default_ease_type or tween._ease_args != ease_args:
                    tween._ease_source, tween._ease_args = self.default_ease_type, ease_args
                    tween._assign_ease(resolve_ease(tween._ease_source, *ease_args, duration=lambda: tween._ease_duration))
            if not tween._auto_kill_configured:
                tween.auto_kill = self.default_auto_kill
            if not tween._loops_configured:
                tween.loop_type = self.default_loop_type
            tween.playing = (self.default_auto_play == AutoPlay.ALL
                             or self.default_auto_play == (AutoPlay.AUTO_PLAY_SEQUENCES if isinstance(tween, Sequence)
                                                          else AutoPlay.AUTO_PLAY_TWEENERS))
        elif not already_owned:
            tween._owner._remove(tween)
        tween._owner = self
        tween._callback_manager = self
        self._tweens[tween] = None
        if not already_owned:
            tween._dispatch_order = self._next_dispatch_order
            self._next_dispatch_order += 1
            self._active_by_phase[tween.update_type] += 1
            kind = int(isinstance(tween, Sequence))
            self._active_counts[kind] += 1
            self._peak_counts[kind] = max(self._peak_counts[kind], self._active_counts[kind])
        if tween.playing:
            self._resume(tween)
        return tween

    @overload
    def to(self, getter: Callable[[], _Value], setter: Callable[[_Value], None], end_value: _Value, duration: float) -> Tweener: ...
    @overload
    def to(self, setter: Callable[[_Value], None], start_value: _Value, end_value: _Value, duration: float) -> Tweener: ...
    @overload
    def to(self, plugin: "AbsTweenPlugin", getter: Callable[[], _Value], setter: Callable[[_Value], None], end_value: object, duration: float) -> "TweenerCore": ...
    def to(self, *args, **kwargs):
        from .plugin import AbsTweenPlugin, _PluginTweenerCore
        if len(args) == 5 or "plugin" in kwargs or args and (args[0] is None or isinstance(args[0], AbsTweenPlugin)):
            plugin, getter, setter, end_value, duration = _bind_arguments(
                ("plugin", "getter", "setter", "end_value", "duration"), args, kwargs)
            if plugin is None:
                return self._to(getter, setter, end_value, duration)
            if not isinstance(plugin, AbsTweenPlugin):
                raise TypeError("plugin must be AbsTweenPlugin or None")
            if not callable(getter) or not callable(setter):
                raise TypeError("getter and setter must be callable")
            if not isfinite(duration) or duration < 0:
                raise ValueError("Duration must be finite and nonnegative")
            from ._builtin_plugins import _BUILTIN_PLUGIN_TYPES
            if type(plugin) in _BUILTIN_PLUGIN_TYPES:
                # An explicitly supplied built-in uses the same prepared native
                # sampler as the ordinary To overload, not per-frame callbacks.
                if plugin.kind == 'array':
                    tween = self.add(self._new(_ArrayTweener, getter, setter, end_value, None, duration))
                elif plugin.kind == 'euler':
                    from .rotation import EulerTweener
                    tween = self.add(self._new(EulerTweener, getter, setter, end_value, duration))
                else:
                    end_value = plugin.convert_to_start_value(None, end_value)
                    tween = self._to(getter, setter, end_value, duration)
                    tween._integer_bits = plugin.bits
                    tween._core_input_type = plugin.value_type
                tween._explicit_builtin_plugin = plugin
                return tween
            from .circle import CirclePlugin, CircleTweener
            from .path import PathPlugin, PathTween
            from .rect import RectOffsetPlugin, RectOffsetTweener
            if type(plugin) is RectOffsetPlugin:
                return self.add(self._new(RectOffsetTweener, getter, setter, end_value, duration, plugin))
            if isinstance(plugin, PathPlugin):
                return self.add(PathTween._from_plugin(getter, setter, end_value, duration))
            kind = CircleTweener if isinstance(plugin, CirclePlugin) else _PluginTweenerCore
            key = (kind, plugin.value_type, plugin.storage_type, plugin.options_type)
            return self.add(self._new(kind, plugin, getter, setter, end_value, duration, pool_key=key))
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
        from infernux.screen import Rect, RectOffset
        if isinstance(end_value, RectOffset):
            from .rect import RectOffsetTweener
            return self.add(self._new(RectOffsetTweener, getter, setter, end_value, duration))
        if isinstance(end_value, Rect):
            from .rect import RectTweener
            return self.add(self._new(RectTweener, getter, setter, end_value, duration))
        if isinstance(end_value, str):
            from .string import StringTweener
            return self.add(self._new(StringTweener, getter, setter, end_value, duration))
        if isinstance(end_value, quatf):
            from .rotation import QuaternionTweener
            return self.add(self._new(QuaternionTweener, getter, setter, end_value, duration))
        kind = _NUMPY_TWEENERS.get(type(end_value))
        if kind is None:
            kind = (_ColorTweener if isinstance(end_value, list) and len(end_value) == 4 else
                    _VectorTweener if isinstance(end_value, (Vector2, Vector3, vec4f, tuple, list)) else _FloatTweener)
        return self.add(self._new(kind, getter, setter, end_value, duration))

    def to_axis(self, getter, setter, end_value, duration, axis_constraint=AxisConstraint.X):
        from infernux.lib import Vector3
        if not isinstance(axis_constraint, AxisConstraint):
            raise TypeError("axis_constraint must be AxisConstraint")
        return self._to(getter, setter, Vector3(end_value, end_value, end_value), duration).set_options(axis_constraint)

    def to_alpha(self, getter, setter, end_value, duration):
        return self._to(getter, setter, [0.0, 0.0, 0.0, end_value], duration).set_options(True)

    def to_array(self, getter, setter, end_values, durations):
        return self.add(self._new(_ArrayTweener, getter, setter, end_values, durations))

    def punch(self, getter, setter, direction, duration, vibrato=10, elasticity=1):
        from .motion import _punch_tween
        tween = _punch_tween(getter, setter, direction, duration, vibrato, elasticity, manager=self)
        return None if tween is None else self.add(tween)

    @overload
    def shake(self, getter: Callable[[], Vector3], setter: Callable[[Vector3], None], duration: float,
              strength: float=3., vibrato: int=10, randomness: float=90., ignore_z_axis: bool=True,
              fade_out: bool=True, randomness_mode: "ShakeRandomnessMode"=...): ...
    @overload
    def shake(self, getter: Callable[[], Vector3], setter: Callable[[Vector3], None], duration: float,
              strength: Vector3, vibrato: int=10, randomness: float=90., fade_out: bool=True,
              randomness_mode: "ShakeRandomnessMode"=...): ...
    def shake(self, getter, setter, duration, *args, **kwargs):
        from .motion import _shake_tween
        tween = _shake_tween(getter, setter, duration, *args, manager=self, **kwargs)
        return None if tween is None else self.add(tween)

    @overload
    def sequence(self): ...
    @overload
    def sequence(self, target: object): ...
    def sequence(self, target=_UNSET):
        sequence = self.add(self._new(Sequence))
        return sequence if target is _UNSET else sequence.set_target(target)

    def _remove(self, tween):
        if tween in self._tweens:
            self._active_counts[int(isinstance(tween, Sequence))] -= 1
            self._active_by_phase[tween.update_type] -= 1
            del self._tweens[tween]
        self._pause(tween)
        tween._owner = None

    def _pause(self, tween):
        running = self._running[tween.update_type]
        if tween in running:
            self._playing_counts[tween.update_type] -= running.pop(tween)
            self._running_snapshots[tween.update_type] = None
            if not running and self._on_activity is not None:
                self._on_activity(tween.update_type, False)

    def _resume(self, tween):
        running = self._running[tween.update_type]
        if tween in running:
            return
        was_empty = not running
        running[tween] = tween.playing
        self._playing_counts[tween.update_type] += tween.playing
        self._running_snapshots[tween.update_type] = None
        for context in self._dispatch_contexts:
            context.resume(tween)
        if was_empty and self._on_activity is not None:
            self._on_activity(tween.update_type, True)

    def _move(self, tween, previous):
        if previous == tween.update_type:
            return
        self._active_by_phase[previous] -= 1
        self._active_by_phase[tween.update_type] += 1
        running = self._running[previous]
        if tween in running:
            self._playing_counts[previous] -= running.pop(tween)
            self._running_snapshots[previous] = None
            if not running and self._on_activity is not None:
                self._on_activity(previous, False)
        if tween.playing:
            self._resume(tween)

    def update(self, delta, unscaled_delta=None, update_type=UpdateType.NORMAL):
        delta = _f32(delta)
        if not isfinite(delta) or delta < 0:
            raise ValueError("Delta must be finite and nonnegative")
        unscaled = delta if unscaled_delta is None else _f32(unscaled_delta)
        if not isfinite(unscaled) or unscaled < 0:
            raise ValueError("Unscaled delta must be finite and nonnegative")
        self._dispatch(delta, unscaled, UpdateType(update_type))

    def _dispatch(self, delta, unscaled, phase):
        """Execute clocks and a phase already supplied by the engine scheduler."""
        # The driver passes two float clocks into the update loop. Callbacks
        # affect global scales on the next call, but own scales remain live.
        scaled = _f32(delta * self._time_scale)
        unscaled = _f32(unscaled * self._unscaled_time_scale * self._time_scale)
        self._update_depth += 1
        context = _DispatchCursor(phase, self._next_dispatch_order)
        contexts = self._dispatch_contexts
        contexts.append(context)
        try:
            snapshot = self._running_snapshots[phase]
            if snapshot is None:
                # Existing roots keep their global creation slot across phases.
                # Mutations enqueue only newly runnable roots ahead of the cursor.
                snapshot = self._running_snapshots[phase] = tuple(
                    (tween._dispatch_order, tween, tween._generation)
                    for tween in sorted(self._running[phase], key=lambda item: item._dispatch_order))
            for _, tween, generation in context.entries(snapshot):
                if tween._generation != generation or tween._owner is not self or tween.update_type != phase:
                    continue
                if not tween._active:
                    self._pending_kills[tween] = generation
                    continue
                try:
                    tween._advance(unscaled if tween.independent else scaled)
                except _TweenNumericOverflow:
                    raise
                except Exception as error:
                    if not self.use_safe_mode:
                        raise
                    tween._kill(at_update_end=True)
                    self._record_error(error)
        finally:
            contexts.pop()
            if contexts is self._dispatch_contexts:
                self._update_depth -= 1
                if not self._update_depth and self._pending_kills:
                    pending, self._pending_kills = self._pending_kills, {}
                    for tween in reversed(pending):
                        if tween._owner is self and tween._generation == pending[tween]:
                            tween._despawn(self)
                if not self._update_depth and self._pending_commits:
                    commits, self._pending_commits = self._pending_commits, {}
                    for receiver in commits.values():
                        receiver.apply()

    def _record_error(self, error):
        self._safe_mode_errors += 1
        level = SafeModeLogBehaviour(self.safe_mode_log_behaviour)
        if level == SafeModeLogBehaviour.NONE:
            return
        if self.log_behaviour == LogBehaviour.ERRORS_ONLY and level != SafeModeLogBehaviour.ERROR:
            return
        from infernux.debug import Debug, LogType
        message = f"Tween safe mode: {error}"
        # The hook receives Log even when the final safe-mode
        # entry is a Warning or Error. Preserve the measured callback contract.
        if self.on_will_log is not None and not self.on_will_log(LogType.LOG, message):
            return
        emit = {
            SafeModeLogBehaviour.NORMAL: Debug.log,
            SafeModeLogBehaviour.WARNING: Debug.log_warning,
            SafeModeLogBehaviour.ERROR: Debug.log_error,
        }[level]
        emit(message)

    def _defer_commit(self, receiver):
        if self._update_depth:
            self._pending_commits[receiver._commit_key] = receiver
        else:
            receiver.apply()

    def manual_update(self, delta_time, unscaled_delta_time):
        self.update(delta_time, unscaled_delta_time, UpdateType.MANUAL)

    def _matching(self, target_or_id=_UNSET, id=_UNSET):
        if target_or_id is None:
            return ()
        return tuple(tween for tween in self._tweens
                     if ((tween.target is not None and _object_equal(target_or_id, tween.target) and _matches_id(tween, id)) if id is not _UNSET else
                         target_or_id is _UNSET or _matches_target_or_id(tween, target_or_id)))

    def _control(self, action, target_or_id=_UNSET, *args, id=_UNSET):
        matching = self._matching(target_or_id, id)
        affected = 0
        for tween in matching:
            if action in ('play', 'play_forward', 'play_backwards'):
                affected += tween._play(None if action == 'play' else action == 'play_backwards')
                continue
            if action == 'toggle_pause' and not tween.playing:
                affected += tween._play()
                continue
            if action == 'pause' and not tween.playing:
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
        matching = [t for t in self._matching() if not any(_matches_exclusion(t, item) for item in ids_or_targets_to_exclude)]
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
        if target_or_id is None and any(t.id is not None or t.target is not None for t in self._matching()):
            raise TypeError("is_tweening requires a non-null target or ID")
        return any(not also_check_if_is_playing or tween.playing for tween in self._matching(target_or_id))

    def tweens_by_id(self, id, playing_only=False, fillable_list=None):
        return _fill_list((tween for tween in self._matching()
                           if _matches_id(tween, id) and (not playing_only or tween.playing)), fillable_list)

    def tweens_by_target(self, target, playing_only=False, fillable_list=None):
        return _fill_list((tween for tween in self._matching()
                           if tween.target is target and (not playing_only or tween.playing)), fillable_list)

    def playing_tweens(self, fillable_list=None):
        return _fill_list((tween for tween in self._matching() if tween.playing), fillable_list)

    def paused_tweens(self, fillable_list=None):
        return _fill_list((tween for tween in self._matching() if not tween.playing), fillable_list)

    def total_active_tweens(self): return self._active_counts[0] + self._active_counts[1]
    def total_active_tweeners(self): return self._active_counts[0]
    def total_active_sequences(self): return self._active_counts[1]
    def total_tweens_by_id(self, id, playing_only=False):
        return sum(_matches_id(tween, id) and (not playing_only or tween.playing) for tween in self._matching())
    def total_playing_tweens(self): return sum(self._playing_counts.values())

    def get_diagnostics(self):
        phases = {phase.name: {"active": self._active_by_phase[phase], "playing": self._playing_counts[phase]}
                  for phase in UpdateType}
        return {"active": sum(item["active"] for item in phases.values()),
                "playing": sum(item["playing"] for item in phases.values()), "phases": phases}

    def get_editor_report(self):
        """Read root peaks and handled failures without traversing live tweens."""
        return {"peak_tweeners": self._peak_counts[0], "peak_sequences": self._peak_counts[1],
                "safe_mode_errors": self._safe_mode_errors}

    def _reset_editor_report(self):
        self._peak_counts[:] = self._active_counts
        self._safe_mode_errors = 0

    def clear(self, destroy=False):
        for tween in tuple(self._tweens):
            if tween._owner is self:
                if tween._active:
                    tween._active = False
                    tween._emit('kill')
                if tween._link is not None:
                    tween._link.detach(tween)
                tween._notify_waiters()
                tween._owner = None
        self._tweens.clear()
        self._pending_kills.clear()
        self._active_counts[:] = (0, 0)
        for phase, running in self._running.items():
            was_running = bool(running)
            running.clear()
            self._running_snapshots[phase] = None
            self._playing_counts[phase] = self._active_by_phase[phase] = 0
            if was_running and self._on_activity is not None:
                self._on_activity(phase, False)
        self.clear_cached_tweens()
        if destroy:
            self.__init__(self._on_activity)


def _object_equal(left, right):
    # CLR object Equals does not equate boxed bool/int/float values. Python's
    # True == 1 == 1.0 must not merge their object-ID groups.
    if type(left) in (bool, int, float) and type(right) in (bool, int, float) and type(left) is not type(right):
        return False
    return left == right


def _matches_id(tween, value):
    if isinstance(value, str):
        return tween.string_id is not None and tween.string_id == value
    if _is_int_id(value):
        return tween.int_id == value
    return tween.id is not None and _object_equal(value, tween.id)


def _matches_target_or_id(tween, value):
    if value is None:
        return False
    if isinstance(value, str) or _is_int_id(value):
        return _matches_id(tween, value)
    return _matches_id(tween, value) or (tween.target is not None and _object_equal(value, tween.target))


def _matches_exclusion(tween, value):
    return _matches_id(tween, value) or (tween.target is not None and _object_equal(value, tween.target)) or (tween.id is not None and _object_equal(value, tween.id))


def _fill_list(items, fillable_list):
    result = [] if fillable_list is None else fillable_list
    result.clear()
    result.extend(items)
    return result if result or fillable_list is not None else None


def _bind_arguments(names, args, kwargs, defaults=None):
    if not kwargs and len(args) == len(names):
        return args
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
        settings = self._settings = Tween(0)
        defaults = _default_manager
        settings.recyclable = defaults.default_recyclable
        settings.auto_kill, settings.loop_type = defaults.default_auto_kill, defaults.default_loop_type
        settings.update_type, settings.independent = defaults.default_update_type, defaults.default_time_scale_independent
        settings._ease_source = Ease.UNSET
        settings._ease_args = defaults.default_ease_overshoot_or_amplitude, defaults.default_ease_period
        return self

    def _set(self, name, *args, **kwargs):
        getattr(self._settings, name)(*args, **kwargs)
        return self

    @overload
    def set_id(self, object_id: object): ...
    @overload
    def set_id(self, *, string_id: str | None): ...
    @overload
    def set_id(self, *, int_id: int): ...
    def set_id(self, *args, **kwargs): return self._set("set_id", *args, **kwargs)
    def set_target(self, target): return self._set("set_target", target)
    def set_auto_kill(self, auto_kill_on_completion=True): return self._set("set_auto_kill", auto_kill_on_completion)
    def set_recyclable(self, recyclable=True): return self._set("set_recyclable", recyclable)
    def set_loops(self, loops: int, loop_type: LoopType | None=None):
        return self._set("set_loops", loops, _UNSET if loop_type is None else loop_type)
    def set_delay(self, delay): return self._set("set_delay", delay)
    def set_relative(self, is_relative=True): return self._set("set_relative", is_relative)
    @overload
    def set_update(self, is_independent_update: bool): ...
    @overload
    def set_update(self, update_type: UpdateType, is_independent_update: bool=False): ...
    def set_update(self, *args, **kwargs):
        if ((args and isinstance(args[0], UpdateType)) or "update_type" in kwargs):
            if len(args) < 2 and "is_independent_update" not in kwargs:
                kwargs["is_independent_update"] = False
        return self._set("set_update", *args, **kwargs)
    @overload
    def set_ease(self, ease: Ease, overshoot_or_amplitude: float | None=None, period: float | None=None): ...
    @overload
    def set_ease(self, anim_curve: AnimationCurve): ...
    @overload
    def set_ease(self, custom_ease: Callable[[float, float, float, float], float]): ...
    def set_ease(self, ease=_UNSET, overshoot_or_amplitude=None, period=None, **kwargs):
        if isinstance(ease, Ease):
            if kwargs:
                raise TypeError("set_ease expects ease, overshoot_or_amplitude and period")
            amplitude = (_default_manager.default_ease_overshoot_or_amplitude
                         if overshoot_or_amplitude is None else overshoot_or_amplitude)
            period = _default_manager.default_ease_period if period is None else period
            return self._set("set_ease", ease, amplitude, period)
        if overshoot_or_amplitude is not None or period is not None:
            raise TypeError("numeric ease parameters require Ease")
        return self._set("set_ease", ease, **kwargs)
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
TweenParams.params = TweenParams()

# Typed scalar storage extends the timeline after its base classes are defined.
from .scalar import _NUMPY_TWEENERS

from .array import _ArrayTweener
