"""Seekable procedural motion and additive displacement."""
from math import cos, isfinite, pi, sin
from enum import Enum
from functools import singledispatch
from typing import overload

from infernux.components.builtin import Camera, Rigidbody
from infernux.debug import Debug
from infernux.lib import Random, Transform, Vector2, Vector3, quatf
from infernux.lib._Infernux import _tween_impulse_durations

from .core import _default_manager, _ArrayTweener, _VectorTweener, _f32, AxisConstraint, LoopType
from .ease import Ease
from .rotation import RotateMode, _rotate_offset
from .spiral import SpiralMode, SpiralPlugin


class ShakeRandomnessMode(Enum):
    FULL = 0
    HARMONIC = 1


def _vector(value):
    return Vector3(value, value, value) if isinstance(value, (int, float)) else Vector3(*value)


class _JumpVerticalTween(_VectorTweener):
    """Keep the reference's float loop clock and the observable Y offset clock."""

    @property
    def full_duration(self):
        return _f32(super().full_duration)

    def _clock(self, position):
        elapsed = _f32(max(0.0, position - self._delay))
        if self._duration == 0 or elapsed >= self.full_duration:
            return self._loops - 1, self._duration
        cycle = int(_f32(elapsed / self._duration))
        remainder = _f32(elapsed % self._duration)
        if elapsed > 0 and remainder == 0:
            return cycle - 1, self._duration
        return cycle, remainder

    @property
    def position(self) -> float:
        return self._clock(self._position)[1]

    def _progress_at(self, position):
        if self._duration == 0:
            return self._loops - 1, 1.0
        cycle, remainder = self._clock(position)
        progress = _f32(remainder / self._duration)
        return cycle, 1 - progress if self.loop_type == LoopType.YOYO and cycle % 2 else progress

    def elapsed(self, include_loops=True):
        if not self._active:
            return 0.0
        cycle, remainder = self._clock(self._position)
        return _f32(_f32(cycle * self._duration) + remainder) if include_loops else remainder


def _jump(target, name, end_value, jump_power, num_jumps, duration, snapping):
    if type(num_jumps) is not int:
        raise TypeError("num_jumps must be an integer")
    num_jumps = max(1, num_jumps)
    planar = isinstance(end_value, Vector2)
    end = Vector2(*end_value) if planar else _vector(end_value)
    read = lambda: getattr(target, name)
    write = target.move_position if isinstance(target, Rigidbody) else lambda value: setattr(target, name, value)
    # Physics and anchored jumps capture height on Start; seeking does not
    # invoke Start. The ordinary Transform shortcut captures height eagerly.
    start_y, offset_y = (0.0 if planar or isinstance(target, Rigidbody) else read().y), None
    sequence = _default_manager.sequence().set_target(target).set_ease(_default_manager.default_ease_type)

    def capture_start():
        nonlocal start_y
        start_y = read().y

    vertical = (_default_manager.add(_default_manager._new(
                    _JumpVerticalTween, read, write, Vector2(0, jump_power) if planar else Vector3(0, jump_power, 0), _f32(duration / (num_jumps * 2))))
                .set_options(AxisConstraint.Y, snapping).set_ease(Ease.OUT_QUAD).set_relative()
                .set_loops(num_jumps * 2, LoopType.YOYO).on_start(capture_start))
    horizontal = (_default_manager.to(read, write, Vector2(end.x, 0) if planar else Vector3(end.x, 0, 0), duration)
                  .set_options(AxisConstraint.X, snapping).set_ease(Ease.LINEAR))
    sequence.append(horizontal)
    if not planar:
        depth = (_default_manager.to(read, write, Vector3(0, 0, end.z), duration)
                 .set_options(AxisConstraint.Z, snapping).set_ease(Ease.LINEAR))
        sequence.join(depth)
    sequence.join(vertical)

    def apply_height_offset():
        nonlocal offset_y
        if offset_y is None:
            offset_y = end.y if sequence._relative else end.y - start_y
        progress = sequence.elapsed_percentage() if planar else vertical.elapsed_percentage()
        position = read()
        position.y += offset_y * progress * (2 - progress)
        write(position)

    vertical.on_update(apply_height_offset)
    return sequence


def twn_jump(target, end_value, jump_power, num_jumps, duration, snapping=False):
    return _jump(target, "position", end_value, jump_power, num_jumps, duration, snapping)


def twn_local_jump(target, end_value, jump_power, num_jumps, duration, snapping=False):
    return _jump(target, "local_position", end_value, jump_power, num_jumps, duration, snapping)


def _impulse_durations(duration, vibrato, fade_out):
    if type(vibrato) is not int:
        raise TypeError("vibrato must be an integer")
    return _tween_impulse_durations(duration, vibrato, fade_out)


def _impulse_tween(getter, setter, offsets, durations, mode, manager=None):
    owner = _default_manager if manager is None else manager
    tween = owner._new(_ArrayTweener, getter, setter, offsets, durations)
    tween._duration = _f32(tween._duration)
    tween._refresh_full_duration()
    tween._startup_mode, tween._startup_offsets = mode, tuple(offsets)
    return tween


def _punch_tween(getter, setter, direction, duration, vibrato=10, elasticity=1.0, *, manager=None):
    duration = _f32(duration)
    durations = _impulse_durations(duration, vibrato, True)
    direction = _vector(direction)
    count = len(durations)
    elasticity = min(1.0, max(0.0, elasticity))
    strength = direction.magnitude
    decay = _f32(strength / count)
    normalized = direction.normalized
    offsets = []
    for index in range(count - 1):
        amplitude = _f32(-strength * elasticity) if index % 2 else strength
        offsets.append(direction if index == 0 else normalized * amplitude)
        strength = _f32(strength - decay)
    offsets.append(Vector3(0, 0, 0))
    return _impulse_tween(getter, setter, offsets, durations, "punch", manager)


def _punch(target, name, punch, duration, vibrato=10, elasticity=1.0, snapping=False):
    if duration <= 0:
        return None
    tween = _punch_tween(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                         punch, duration, vibrato, elasticity)
    if tween is None:
        return None
    tween.set_target(target)
    tween._snapping = snapping
    return _default_manager.add(tween)


def twn_punch_position(target, punch, duration, vibrato=10, elasticity=1.0, snapping=False):
    return _punch(target, "local_position", punch, duration, vibrato, elasticity, snapping)


def twn_punch_rotation(target, punch, duration, vibrato=10, elasticity=1.0):
    return _punch(target, "local_euler_angles", punch, duration, vibrato, elasticity)


def twn_punch_scale(target, punch, duration, vibrato=10, elasticity=1.0):
    return _punch(target, "local_scale", punch, duration, vibrato, elasticity)


def _clamp_magnitude(value, limit):
    magnitude = value.magnitude
    return value / magnitude * limit if value.sqr_magnitude > _f32(limit * limit) else value


def _shake_offsets(duration, strength, vibrato, randomness, fade_out, randomness_mode, ignore_z_axis=False):
    if not isinstance(randomness_mode, ShakeRandomnessMode):
        raise TypeError("randomness_mode must be ShakeRandomnessMode")
    vector = isinstance(strength, Vector3)
    if not vector and type(strength) not in (int, float):
        raise TypeError("strength must be float or Vector3")
    duration, randomness = _f32(duration), _f32(randomness)
    durations = _impulse_durations(duration, vibrato, fade_out)
    count = len(durations)
    spatial = vector or not ignore_z_axis
    lower = -randomness if randomness_mode == ShakeRandomnessMode.FULL else 0.0
    bounds = [(0.0, 360.0)]
    for index in range(count - 1):
        if index:
            bounds.append((lower, randomness))
        if spatial:
            bounds.append((lower, randomness))
    draws = iter(Random.range_many(bounds))
    angle = next(draws)
    magnitude = strength.magnitude if vector else _f32(strength)
    decay = _f32(magnitude / count)
    offsets = []
    for index in range(count - 1):
        if index:
            angle = _f32(_f32(angle - 180) + next(draws))
        radians = _f32(angle * _f32(pi / 180))
        point = Vector3(_f32(cos(radians)) * magnitude, _f32(sin(radians)) * magnitude, 0)
        if spatial:
            point = _rotate_offset(quatf.angle_axis(next(draws), Vector3(0, 1, 0)), point)
        if vector:
            # Each component clamp observes the previously changed components.
            for axis, limit in enumerate(strength):
                setattr(point, "xyz"[axis], _clamp_magnitude(point, limit)[axis])
            point = point / point.magnitude * magnitude if point.magnitude > 1e-5 else Vector3(0, 0, 0)
        offsets.append(point)
        if fade_out:
            magnitude = _f32(magnitude - decay)
        if vector:
            strength = _clamp_magnitude(strength, magnitude)
    offsets.append(Vector3(0, 0, 0))
    return offsets, durations


@overload
def _shake_tween(getter, setter, duration: float, strength: float=3, vibrato: int=10,
                 randomness: float=90, ignore_z_axis: bool=True, fade_out: bool=True,
                 randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def _shake_tween(getter, setter, duration: float, strength: Vector3, vibrato: int=10,
                 randomness: float=90, fade_out: bool=True,
                 randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
def _shake_tween(getter, setter, duration, *args, manager=None, **kwargs):
    strength = args[0] if args else kwargs.get("strength", 3.0)
    vector = isinstance(strength, Vector3)
    names = ["strength", "vibrato", "randomness", *([] if vector else ["ignore_z_axis"]), "fade_out", "randomness_mode"]
    if len(args) > len(names) or any(name not in names for name in kwargs):
        raise TypeError("invalid shake overload")
    values = dict(zip(names, args))
    if values.keys() & kwargs.keys():
        raise TypeError("duplicate shake argument")
    values.update(kwargs)
    strength = values.get("strength", 3.0)
    if not vector and (type(strength) not in (int, float)):
        raise TypeError("strength must be float or Vector3")
    offsets, durations = _shake_offsets(duration, strength, values.get("vibrato", 10), values.get("randomness", 90),
                                         values.get("fade_out", True), values.get("randomness_mode", ShakeRandomnessMode.FULL),
                                         values.get("ignore_z_axis", True))
    return _impulse_tween(getter, setter, offsets, durations, "shake", manager)


def _shake(target, name, duration, strength, vibrato, randomness, snapping, fade_out, randomness_mode):
    if duration <= 0:
        return None
    offsets, durations = _shake_offsets(duration, strength, vibrato, randomness, fade_out, randomness_mode)
    tween = _impulse_tween(lambda: getattr(target, name), lambda value: setattr(target, name, value), offsets, durations, "shake")
    return _default_manager.add(tween).set_options(snapping).set_target(target)


@overload
def twn_shake_position(target: Transform, duration: float, strength: float=1, vibrato: int=10,
                      randomness: float=90, snapping: bool=False, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def twn_shake_position(target: Transform, duration: float, strength: Vector3, vibrato: int=10,
                      randomness: float=90, snapping: bool=False, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def twn_shake_position(target: Camera, duration: float, strength: float=3, vibrato: int=10,
                      randomness: float=90, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def twn_shake_position(target: Camera, duration: float, strength: Vector3, vibrato: int=10,
                      randomness: float=90, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@singledispatch
def twn_shake_position(target, duration, strength=1.0, vibrato=10, randomness=90, snapping=False,
                      fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    return _shake(target, "local_position", duration, strength, vibrato, randomness, snapping, fade_out, randomness_mode)


@twn_shake_position.register(Camera)
def _camera_shake_position(target, duration, strength=3.0, vibrato=10, randomness=90,
                           fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    if duration <= 0:
        return None
    offsets, durations = _shake_offsets(duration, strength, vibrato, randomness, fade_out, randomness_mode, True)
    tween = _impulse_tween(lambda: target.transform.local_position,
                           lambda value: setattr(target.transform, "local_position", value), offsets, durations, "shake")
    tween._startup_rotation_getter = lambda: target.transform.local_rotation
    return _default_manager.add(tween).set_target(target)


def twn_shake_rotation(target, duration, strength=90.0, vibrato=10, randomness=90,
                      fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    transform = target.transform if isinstance(target, Camera) else target
    tween = _shake(transform, "local_euler_angles", duration, strength, vibrato, randomness,
                   False, fade_out, randomness_mode)
    return None if tween is None else tween.set_target(target)


def twn_shake_scale(target, duration, strength=1.0, vibrato=10, randomness=90,
                   fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    return _shake(target, "local_scale", duration, strength, vibrato, randomness, False, fade_out, randomness_mode)


def _blendable(target, name, by_value, duration, snapping=False):
    applied = Vector3(0, 0, 0)
    def write(displacement):
        nonlocal applied
        setattr(target, name, getattr(target, name)+displacement-applied)
        applied = displacement
    return _default_manager.to(lambda: Vector3(0, 0, 0), write, _vector(by_value), duration).set_options(snapping).set_target(target)


def twn_blendable_move_by(target, by_value, duration, snapping=False): return _blendable(target, "position", by_value, duration, snapping)
def twn_blendable_local_move_by(target, by_value, duration, snapping=False): return _blendable(target, "local_position", by_value, duration, snapping)
def twn_blendable_scale_by(target, by_value, duration): return _blendable(target, "local_scale", by_value, duration)


def _blendable_rotation(target, name, by, duration, mode):
    if not isinstance(mode, RotateMode):
        raise TypeError("mode must be RotateMode")
    by = _vector(by)
    if mode == RotateMode.FAST:
        wrapped = [(value+180) % 360-180 for value in by]
        by = Vector3(*(180 if item == -180 and value > 0 else item for item, value in zip(wrapped, by)))
    return _default_manager.to(lambda: Vector3(0, 0, 0), _rotation_writer(target, name, mode), by, duration).set_target(target)


def _rotation_writer(target, name, mode):
    applied = quatf.identity()
    local = mode == RotateMode.LOCAL_AXIS_ADD or mode != RotateMode.WORLD_AXIS_ADD and name == "local_rotation"
    def write(value):
        nonlocal applied
        rotation = quatf.euler(*value)
        current = getattr(target, name)
        value = current*quatf.inverse(applied)*rotation if local else rotation*quatf.inverse(applied)*current
        setattr(target, name, value)
        applied = rotation
    return write


def twn_blendable_rotate_by(target, by_value, duration, mode=RotateMode.FAST):
    return _blendable_rotation(target, "rotation", by_value, duration, mode)


def twn_blendable_local_rotate_by(target, by_value, duration, mode=RotateMode.FAST):
    return _blendable_rotation(target, "local_rotation", by_value, duration, mode)


def twn_blendable_punch_rotation(target, punch: Vector3, duration: float, vibrato: int=10, elasticity: float=1):
    if duration <= 0:
        return None
    writer = _rotation_writer(target, "local_rotation", RotateMode.LOCAL_AXIS_ADD)
    tween = _punch_tween(lambda: Vector3(0, 0, 0), writer, punch, duration, vibrato, elasticity)
    return None if tween is None else _default_manager.add(tween).set_target(target)


def twn_spiral(target, duration, axis=None, mode=SpiralMode.EXPAND, speed=1.0, frequency=10.0, depth=0.0, snapping=False):
    if not isinstance(mode, SpiralMode):
        raise TypeError("mode must be SpiralMode")
    if not isinstance(target, (Transform, Rigidbody)):
        raise TypeError("Spiral target must be Transform or Rigidbody")
    axis = SpiralPlugin.default_direction if axis is None else _vector(axis)
    if axis.sqr_magnitude < 1e-10:  # Unity Vector3 equality, not exact component equality.
        axis = SpiralPlugin.default_direction
    speed = _f32(speed)
    if abs(speed) < 8 * _f32(1.401298464324817e-45):
        speed = 1.0
    name = "position" if isinstance(target, Rigidbody) else "local_position"
    apply = target.move_position if isinstance(target, Rigidbody) else lambda value: setattr(target, name, value)

    def write(value):
        # Unity rejects an invalid Transform/physics assignment. Keep that
        # shortcut behavior without changing what a generic plugin setter sees.
        if all(isfinite(component) for component in value):
            apply(value)
        else:
            Debug.log_error("Spiral produced a nonfinite position; the target pose was retained", context=target)

    tween = _default_manager.to(SpiralPlugin.get(), lambda: getattr(target, name), write, axis, _f32(duration)).set_target(target)
    options = tween.plug_options
    options.mode, options.speed = mode, speed
    options.frequency, options.depth, options.snapping = _f32(frequency), _f32(depth), snapping
    return tween
