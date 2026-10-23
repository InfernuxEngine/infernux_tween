from enum import Enum

from infernux.lib import Vector3, quatf

from .core import _default_manager, LoopType, Tweener, UpdateType, _UNSET


class RotateMode(Enum):
    FAST = "Fast"
    FAST_BEYOND360 = "FastBeyond360"
    WORLD_AXIS_ADD = "WorldAxisAdd"
    LOCAL_AXIS_ADD = "LocalAxisAdd"


def _sample_euler(tween, value, factor):
    mode = tween._rotate_mode
    if mode in (RotateMode.WORLD_AXIS_ADD, RotateMode.LOCAL_AXIS_ADD):
        initial, delta = quatf.euler(*tween._start), quatf.euler(*(tween._delta * factor))
        return delta * initial if mode == RotateMode.WORLD_AXIS_ADD else initial * delta
    return quatf.euler(*value)


class EulerTweener(Tweener):
    def __init__(self, getter, setter, end_value, duration, mode=RotateMode.FAST):
        if not isinstance(mode, RotateMode):
            raise TypeError("mode must be RotateMode")
        super().__init__(getter, setter, end_value, duration)
        self._rotate_mode = mode

    def set_options(self, use_shortest360_route: bool=True):
        if not self._configure():
            return self
        if type(use_shortest360_route) is not bool:
            raise TypeError("use_shortest360_route must be bool")
        self._rotate_mode = RotateMode.FAST if use_shortest360_route else RotateMode.FAST_BEYOND360
        if self._start is not None:
            self._set_values(self._start, self._end)
        return self

    def _capture_values(self):
        if self._from and self._from_value is _UNSET and self._rotate_mode in (RotateMode.WORLD_AXIS_ADD, RotateMode.LOCAL_AXIS_ADD):
            current = self._getter()
            delta = quatf.euler(*self._end)
            start = delta * current if self._rotate_mode == RotateMode.WORLD_AXIS_ADD else current * delta
            self._euler, self._integer, self._sequence_value = True, False, False
            self._sample_rotation = _sample_euler
            self._value_type, self._rotation_start = Vector3, start
            return start.euler_angles, -self._end
        return super()._capture_values()

    def _set_values(self, start, end):
        super()._set_values(start, end)
        if self._rotate_mode in (RotateMode.WORLD_AXIS_ADD, RotateMode.LOCAL_AXIS_ADD) and not self._relative:
            self._delta = end


class QuaternionTweener(Tweener):
    def _relative_value(self, current, value):
        return current * value

    def _set_values(self, start, end):
        self._start, self._end = start.normalized, end.normalized

    def _distance(self):
        return quatf.angle(self._start, self._end)

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        self._setter(quatf.slerp(self._start, self._end, self._ease(progress)))

    def set_loops(self, loops, loop_type=_UNSET):
        if loop_type == LoopType.INCREMENTAL:
            raise ValueError("Use Euler rotation for incremental turns")
        return super().set_loops(loops, loop_type)


def do_rotate_quaternion(target, end_value, duration):
    from infernux.components.builtin import Rigidbody
    setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
    tween = _default_manager.add(QuaternionTweener(lambda: target.rotation, setter, end_value, duration)).set_target(target)
    return tween.set_update(UpdateType.FIXED) if isinstance(target, Rigidbody) else tween


def do_local_rotate_quaternion(target, end_value, duration):
    return _default_manager.add(QuaternionTweener(lambda: target.local_rotation,
                       lambda value: setattr(target, "local_rotation", value), end_value, duration)).set_target(target)
