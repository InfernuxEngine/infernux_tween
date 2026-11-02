from enum import Enum
from typing import overload

from infernux.lib import Vector3, quatf

from .core import _default_manager, _VectorTweener, AxisConstraint, LoopType, _UNSET, _bind_arguments
from .plugin import AbsTweenPlugin, NoOptions, _PluginTweenerCore
from ._builtin_plugins import _Options, _option_field
from infernux.lib._Infernux import _EulerTweenSnapshot, _euler_tween_change, _sample_quaternion_ease


def _rotate_offset(rotation, value):
    rotated = rotation * quatf(value.x, value.y, value.z, 0) * quatf.inverse(rotation)
    return Vector3(rotated.x, rotated.y, rotated.z)


class RotateMode(Enum):
    FAST = 0
    FAST_BEYOND360 = 1
    WORLD_AXIS_ADD = 2
    LOCAL_AXIS_ADD = 3


class QuaternionOptions(_Options):
    _fields = (('rotate_mode', '_rotate_mode'), ('axis_constraint', '_constraint'),
               ('up', '_up'), ('dynamic_look_at', '_dynamic'),
               ('dynamic_look_at_world_position', '_towards'))
    rotate_mode = _option_field('rotate_mode', '_rotate_mode')
    axis_constraint = _option_field('axis_constraint', '_constraint')
    _up_field = _option_field('up', '_up')
    dynamic_look_at = _option_field('dynamic_look_at', '_dynamic')
    _point_field = _option_field('dynamic_look_at_world_position', '_towards')

    @property
    def up(self): return self._up_field

    @up.setter
    def up(self, value): self._up_field = Vector3(*value)

    @property
    def dynamic_look_at_world_position(self): return self._point_field

    @dynamic_look_at_world_position.setter
    def dynamic_look_at_world_position(self, value): self._point_field = Vector3(*value)

    def __init__(self):
        super().__init__()
        self.reset()

    def __copy__(self):
        result = super().__copy__()
        for field in ('up', 'dynamic_look_at_world_position'):
            result._values[field] = Vector3(*getattr(self, field))
        return result

    def reset(self):
        self.rotate_mode = RotateMode.FAST
        self.axis_constraint = AxisConstraint.NONE
        self._up_field = Vector3()
        self.dynamic_look_at = False
        self._point_field = Vector3()


def _select_euler(tween):
    if getattr(tween, '_core_plugin_kind', None) == 'euler':
        return
    tween._core_plugin_kind = 'euler'
    tween._up, tween._towards, tween._dynamic = Vector3(), Vector3(), False
    if tween._rotate_mode is None:
        shortest = tween._use_shortest360_route if tween._vector_option is _UNSET else tween._vector_option
        tween._rotate_mode = RotateMode.FAST if shortest else RotateMode.FAST_BEYOND360


def _compile_euler(tween):
    tween._numeric_value = _EulerTweenSnapshot(tween._start, tween._delta, tween._end, tween._up,
        tween._towards, tween._rotate_mode.value, int(tween._constraint), tween._relative)
    tween._prepare_euler_look = tween._numeric_value.prepare_look_at
    tween._bind_numeric_sampler()


def _apply_euler(tween, progress, cycle, previous, callbacks):
    setter = tween._setter
    if tween._dynamic:
        tween._prepare_euler_look(tween.target.position)
    own = tween._incremental_cycles(cycle, False)
    parent = tween._parent
    if parent is not None and parent.loop_type == LoopType.INCREMENTAL:
        value = tween._sample_parent_incremental(progress, own, parent)
    elif tween._sample_numeric is not None:
        value = tween._sample_numeric(progress, own)
    else:
        value = tween._interpolate_numeric(tween._ease(progress), own)
    setter(value)


def _set_euler_from(tween, *args):
    current = tween.getter()
    mode = tween.plug_options.rotate_mode
    if len(args) == 1:
        previous = tween.end_value
        if mode in (RotateMode.WORLD_AXIS_ADD, RotateMode.LOCAL_AXIS_ADD):
            delta = quatf.euler(*previous)
            first = delta * current if mode == RotateMode.WORLD_AXIS_ADD else current * delta
            tween.start_value, tween.end_value = first.euler_angles, -previous
        else:
            tween.start_value, tween.end_value = previous, current.euler_angles
            if mode == RotateMode.FAST_BEYOND360:
                tween.start_value = tween.start_value + tween.end_value
        immediate = True
    else:
        first, immediate, relative = _bind_arguments(('from_value', 'set_immediately', 'is_relative'), args, {})
        tween.start_value = first
        if relative:
            angles = current.euler_angles
            tween.start_value = tween.start_value + angles
            tween.end_value = tween.end_value + angles
    if immediate:
        tween.setter(quatf.euler(*tween.start_value))


class PureQuaternionPlugin(AbsTweenPlugin[quatf, quatf, NoOptions]):
    """Direct quaternion interpolation with the reference plugin lifecycle.

    Incremental loops repeat the rotation without accumulating another turn.
    Use Euler rotation when accumulated turns are required.
    """
    storage_default = staticmethod(lambda: quatf(0, 0, 0, 0))
    _instance = None

    @classmethod
    def plug(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self, t):
        pass

    @overload
    def set_from(self, t, is_relative: bool): ...
    @overload
    def set_from(self, t, from_value, set_immediately: bool, is_relative: bool): ...
    def set_from(self, t, *args, **kwargs):
        if (len(args) == 1 and not kwargs) or (not args and set(kwargs) == {'is_relative'}):
            relative, = _bind_arguments(('is_relative',), args, kwargs)
            previous = quatf(*t.end_value)
            t.end_value = t.getter()
            start = t.end_value * previous if relative else previous
            t.start_value = start
            t.setter(start)
        else:
            value, immediate, relative = _bind_arguments(('from_value', 'set_immediately', 'is_relative'), args, kwargs)
            value = quatf(*value)
            if relative:
                current = t.getter()
                t.end_value = current * t.end_value
                value = current * value
            t.start_value = value
            if immediate:
                t.setter(value)

    def convert_to_start_value(self, t, value):
        return quatf(*value)

    def set_relative_end_value(self, t):
        t.end_value = t.end_value * t.start_value

    def set_change_value(self, t):
        t.change_value = quatf(*t.end_value)

    def get_speed_based_duration(self, options, units_x_second, change_value):
        return change_value.euler_angles.magnitude / units_x_second

    def evaluate_and_apply(self, options, t, is_relative, getter, setter, elapsed,
                           start_value, change_value, duration, using_inverse_position,
                           new_completed_steps, update_notice):
        setter(_sample_quaternion_ease(start_value, change_value, t._ease_time, elapsed, duration))


class EulerTweener(_VectorTweener):
    _core_plugin_kind = 'euler'
    _apply = _apply_euler
    _compile_numeric_value = _compile_euler

    def __init__(self, getter, setter, end_value, duration, mode=RotateMode.FAST):
        if not isinstance(mode, RotateMode):
            raise TypeError("mode must be RotateMode")
        super().__init__(getter, setter, end_value, duration)
        self._rotate_mode = mode
        self._up, self._towards, self._dynamic = Vector3(), Vector3(), False

    def set_options(self, use_shortest360_route: bool=True):
        if not self._active:
            return self
        if type(use_shortest360_route) is not bool:
            raise TypeError("use_shortest360_route must be bool")
        self._rotate_mode = RotateMode.FAST if use_shortest360_route else RotateMode.FAST_BEYOND360
        if self._start is not None and not self._initialized:
            self._set_values(self._start, self._end)
        elif self._initialized:
            self._compile_numeric_value()
        return self

class QuaternionTweener(_PluginTweenerCore):
    _copy_argument = staticmethod(lambda value: quatf(*value))

    def __init__(self, getter, setter, end_value, duration):
        super().__init__(PureQuaternionPlugin.plug(), getter, setter, quatf(*end_value), duration)

    def _apply(self, progress, cycle, previous, callbacks):
        # Lifecycle/storage are shared with custom plugins. The built-in value
        # route avoids constructing the general plugin callback's argument list.
        if self._numeric_ease is None:
            self._setter(_sample_quaternion_ease(self._start, self._delta, self._ease, progress))
        else:
            self._setter(quatf.slerp(self._start, self._delta, self._ease(progress)))


def twn_rotate_quaternion(target, end_value, duration):
    from infernux.components.builtin import Rigidbody
    setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
    return _default_manager.add(_default_manager._new(QuaternionTweener, lambda: target.rotation, setter,
                                                     end_value, duration)).set_target(target)


def twn_local_rotate_quaternion(target, end_value, duration):
    return _default_manager.add(_default_manager._new(QuaternionTweener, lambda: target.local_rotation,
                       lambda value: setattr(target, "local_rotation", value), end_value, duration)).set_target(target)
