"""Custom interpolation plugins on the shared Tween lifecycle and scheduler."""

from abc import ABC, abstractmethod
from copy import copy
from enum import Enum
from typing import Generic, TypeVar, get_args, get_origin, overload

from .core import LoopType, Tween, TweenerCore, _UNSET, _bind_arguments, _f32

Value = TypeVar("Value")
Storage = TypeVar("Storage")
Options = TypeVar("Options")


def _from_arguments(args, kwargs):
    names = (('from_value', 'set_immediately', 'is_relative')
             if len(args) > 1 or 'from_value' in kwargs or 'set_immediately' in kwargs
             else ('is_relative',))
    return _bind_arguments(names, args, kwargs)


class UpdateNotice(Enum):
    NONE = 0
    REWIND_STEP = 1


class NoOptions:
    _fields = ()

    def reset(self):
        pass


class AbsTweenPlugin(ABC, Generic[Value, Storage, Options]):
    """The reference plugin callbacks, with Python names and overload dispatch.

    Generic arguments declare value, storage and options types. ``storage_default``
    supplies a fresh value-type default when the storage is a Python value object;
    its default is None, appropriate for reference storage. Options must support
    no-argument construction and reset(). Never store per-tween state on a shared
    plugin instance: keep it in the tween's values and plug_options instead.
    """

    value_type = object
    storage_type = object
    options_type = NoOptions
    storage_default = staticmethod(lambda: None)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is AbsTweenPlugin:
                for name, kind in zip(
                    ("value_type", "storage_type", "options_type"), get_args(base)
                ):
                    if isinstance(kind, type) and name not in cls.__dict__:
                        setattr(cls, name, kind)

    @abstractmethod
    def reset(self, t): ...

    @overload
    def set_from(self, t, is_relative: bool): ...
    @overload
    def set_from(self, t, from_value, set_immediately: bool, is_relative: bool): ...
    @abstractmethod
    def set_from(self, t, *args, **kwargs): ...

    @abstractmethod
    def convert_to_start_value(self, t, value): ...

    @abstractmethod
    def set_relative_end_value(self, t): ...

    @abstractmethod
    def set_change_value(self, t): ...

    @abstractmethod
    def get_speed_based_duration(self, options, units_x_second, change_value): ...

    @abstractmethod
    def evaluate_and_apply(
        self,
        options,
        t,
        is_relative,
        getter,
        setter,
        elapsed,
        start_value,
        change_value,
        duration,
        using_inverse_position,
        new_completed_steps,
        update_notice,
    ): ...


class _PluginTweenerCore(TweenerCore):
    # The plugin's Reset owns its storage lifetime. The generic pool must not
    # replace the values just written by that callback with unrelated sentinels.
    _pool_preserved_fields = ("_start", "_end", "_delta")

    def __init__(self, plugin, getter, setter, end_value, duration):
        super().__init__(getter, setter, end_value, duration)
        self.tween_plugin = plugin
        self._start = plugin.storage_default()
        self._delta = plugin.storage_default()
        self._plugin_manual_start = False
        self._plugin_was_complete = False
        # Sequence Goto can remap its previous-time argument when Yoyo reverses.
        # UpdateNotice uses the child's actual previous clock, not that mapping.
        self._plugin_previous_position = 0.0
        self._plug_options = self.__dict__.pop("_retained_plugin_options", None)
        if self._plug_options is None:
            self._plug_options = plugin.options_type()
            self._plug_options.reset()

    def get_plugin(self):
        return self.tween_plugin

    @property
    def plug_options(self):
        return self._plug_options

    @plug_options.setter
    def plug_options(self, value):
        if not isinstance(value, self.tween_plugin.options_type):
            raise TypeError("plug_options must have the plugin's declared options type")
        # Reference options are structs: replacing the options copies fields,
        # while editing tween.plug_options.field mutates the tween's own state.
        self._plug_options = copy(value)

    @property
    def start_value(self):
        return self._start

    @start_value.setter
    def start_value(self, value):
        self._start = self._copy_argument(value)

    @TweenerCore.end_value.setter
    def end_value(self, value):
        self._end = self._copy_argument(value)

    @property
    def change_value(self):
        return self._delta

    @change_value.setter
    def change_value(self, value):
        self._delta = self._copy_argument(value)

    def _ensure_initialized(self):
        if not self._initialized:
            plugin = self.tween_plugin
            if not self._plugin_manual_start:
                if self._from:
                    plugin.set_from(self, self._relative)
                    self._relative = False
                else:
                    self.start_value = plugin.convert_to_start_value(
                        self, self.getter()
                    )
            if self._relative:
                plugin.set_relative_end_value(self)
            plugin.set_change_value(self)
            if self._speed_based:
                self._duration = _f32(plugin.get_speed_based_duration(
                    self.plug_options, self._duration, self.change_value
                ))
        return Tween._ensure_initialized(self)

    def _apply_from(self, from_value, set_immediately, relative):
        self._from, self._from_relative = True, relative
        if from_value is not _UNSET:
            self.tween_plugin.set_from(self, from_value, set_immediately, relative)
            self._plugin_manual_start = True
        elif set_immediately:
            self.tween_plugin.set_from(self, relative)
            self._plugin_manual_start = True
        else:
            self._relative = relative
        return self

    def _change_values(
        self, *, start=_UNSET, end=_UNSET, duration=-1, snap_start=False
    ):
        if not self._active or self._parent is not None:
            return self
        duration = _f32(duration)
        if start is not _UNSET:
            start = self._copy_argument(start)
        if end is not _UNSET:
            end = self._copy_argument(end)
        if start is not _UNSET:
            self.start_value = start
            self._plugin_manual_start = True
        if end is not _UNSET:
            self.end_value = end
            self._relative = False
            if start is not _UNSET:
                self._from = False
            if snap_start and self._initialized:
                self.start_value = self.tween_plugin.convert_to_start_value(
                    self, self.getter()
                )
        if self._initialized:
            self.tween_plugin.set_change_value(self)
        if duration > 0:
            self._duration = _f32(
                self.tween_plugin.get_speed_based_duration(
                    self.plug_options, duration, self.change_value
                )
                if self._speed_based and self._initialized
                else duration
            )
        self._seek_serial += 1
        self._ensure_initialized()
        if self._seek(min(self._position, self._delay), self._position, False, notify_update=False) is False:
            return self
        if self._backwards:
            self.pause()
        return self

    def _apply(self, progress, cycle, previous, callbacks):
        inverse = (self.loop_type == LoopType.YOYO and cycle % 2 != 0) != self._inverted
        steps = (
            abs(
                self.completed_loops()
                - self._completed_loops_at(previous)
            )
            if self._duration and callbacks
            else 0
        )
        notice = (
            UpdateNotice.REWIND_STEP
            if self._is_rewind_step(self._plugin_previous_position)
            else UpdateNotice.NONE
        )
        self._plugin_previous_position = self._position
        if self._duration == 0:
            if callbacks and not self._plugin_was_complete:
                steps = max(1, self._loops)
            elif not callbacks and self._plugin_was_complete:
                notice = UpdateNotice.REWIND_STEP
        self._plugin_was_complete = (
            self._position >= self.full_duration and notice != UpdateNotice.REWIND_STEP
        )
        self.tween_plugin.evaluate_and_apply(
            self.plug_options,
            self,
            self._relative,
            self.getter,
            self.setter,
            progress * self._duration,
            self.start_value,
            self.change_value,
            self._duration,
            inverse,
            steps,
            notice,
        )

    def _on_despawn(self):
        super()._on_despawn()
        self.tween_plugin.reset(self)
        self.plug_options.reset()
        self.getter = self.setter = None

    def _pool_reuse_state(self):
        return {"_retained_plugin_options": self.plug_options}
