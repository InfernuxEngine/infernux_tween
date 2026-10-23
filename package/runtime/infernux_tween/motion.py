"""Seekable procedural motion and additive displacement."""
from math import cos, pi, sin
from enum import Enum
from functools import singledispatch
import random
from typing import overload

from infernux.components.builtin import Camera, Rigidbody
from infernux.lib import Transform, Vector3, quatf

from .core import _default_manager, Tweener, UpdateType
from .ease import Ease
from .rotation import RotateMode


class SpiralMode(Enum):
    EXPAND = "Expand"
    EXPAND_THEN_CONTRACT = "ExpandThenContract"


class ShakeRandomnessMode(Enum):
    FULL = "Full"
    HARMONIC = "Harmonic"


def _vector(value):
    return Vector3(value, value, value) if isinstance(value, (int, float)) else Vector3(*value)


class MotionTween(Tweener):
    def __init__(self, getter, setter, duration, sample, snapping=False):
        super().__init__(getter, setter, Vector3(0, 0, 0), duration)
        self._sample, self._snapping = sample, snapping
        self._no_from = True
        self.set_ease(Ease.LINEAR)

    def _apply(self, progress, cycle, previous, callbacks):
        self.force_init()
        value = self._sample(self._start, self._ease(progress), self._relative)
        increment = self._incremental_cycles(cycle)
        if increment:
            value += (self._sample(self._start, 1.0, self._relative)-self._start)*increment
        if self._snapping:
            value = Vector3(*(round(item) for item in value))
        self._setter(value)


class _ImpulseTween(MotionTween):
    def _initialize(self):
        self._relative = self._speed_based = False
        super()._initialize()


def _target_motion(target, name, duration, sample, snapping=False, tween_type=MotionTween):
    if isinstance(target, Rigidbody):
        if name != "position":
            raise TypeError("Rigidbody procedural motion uses world position")
        setter = target.move_position
    else:
        setter = lambda value: setattr(target, name, value)
    tween = tween_type(lambda: getattr(target, name), setter, duration, sample, snapping).set_target(target)
    if isinstance(target, Rigidbody):
        tween.set_update(UpdateType.FIXED)
    return tween


def _jump(target, name, end_value, jump_power, num_jumps, duration, snapping):
    if int(num_jumps) != num_jumps or num_jumps < 1:
        raise ValueError("Jump count must be a positive integer")
    end = _vector(end_value)
    def sample(start, progress, relative):
        phase = (progress*num_jumps) % 1
        return start+(end if relative else end-start)*progress+Vector3(0, 4*jump_power*phase*(1-phase), 0)
    return _default_manager.sequence().append(_target_motion(target, name, duration, sample, snapping)).set_target(target)


def do_jump(target, end_value, jump_power, num_jumps, duration, snapping=False):
    sequence = _jump(target, "position", end_value, jump_power, num_jumps, duration, snapping)
    return sequence.set_update(UpdateType.FIXED) if isinstance(target, Rigidbody) else sequence


def do_local_jump(target, end_value, jump_power, num_jumps, duration, snapping=False):
    return _jump(target, "local_position", end_value, jump_power, num_jumps, duration, snapping)


def _punch_tween(getter, setter, direction, duration, vibrato=10, elasticity=1.0):
    if duration <= 0:
        return None
    if vibrato < 1 or not 0 <= elasticity <= 1:
        raise ValueError("Punch needs positive vibrato and elasticity in [0, 1]")
    strength = _vector(direction)
    def sample(start, progress, relative):
        wave = sin(progress*pi*2*vibrato)*(1-progress)**2
        return start+strength*(wave if wave >= 0 else wave*elasticity)
    return _ImpulseTween(getter, setter, duration, sample)


def _punch(target, name, punch, duration, vibrato=10, elasticity=1.0, snapping=False):
    tween = _punch_tween(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                         punch, duration, vibrato, elasticity)
    if tween is None:
        return None
    tween.set_target(target)
    tween._snapping = snapping
    return _default_manager.add(tween)


def do_punch_position(target, punch, duration, vibrato=10, elasticity=1.0, snapping=False):
    return _punch(target, "local_position", punch, duration, vibrato, elasticity, snapping)


def do_punch_rotation(target, punch, duration, vibrato=10, elasticity=1.0):
    return _punch(target, "local_euler_angles", punch, duration, vibrato, elasticity)


def do_punch_scale(target, punch, duration, vibrato=10, elasticity=1.0):
    return _punch(target, "local_scale", punch, duration, vibrato, elasticity)


def _shake_sample(strength, vibrato, randomness, fade_out, randomness_mode):
    if int(vibrato) != vibrato or vibrato < 1 or not 0 <= randomness <= 180:
        raise ValueError("Shake needs integer vibrato > 0 and randomness in [0, 180]")
    if not isinstance(randomness_mode, ShakeRandomnessMode):
        raise TypeError("randomness_mode must be ShakeRandomnessMode")
    rng, strength = random.Random(0), _vector(strength)
    points = [Vector3(0, 0, 0)]
    angle = 0.0
    for index in range(vibrato):
        angle += pi+rng.uniform(-randomness, randomness)*pi/180
        tilt = (rng.uniform(-randomness, randomness) if randomness_mode == ShakeRandomnessMode.FULL
                else randomness*sin(index*pi/2))*pi/180
        fade = 1-index/vibrato if fade_out else 1
        points.append(Vector3(cos(angle)*cos(tilt)*strength.x,
                              sin(angle)*cos(tilt)*strength.y, sin(tilt)*strength.z)*fade)
    points.append(Vector3(0, 0, 0))
    def sample(start, progress, relative):
        position = min(1, max(0, progress))*(len(points)-1)
        index = min(len(points)-2, int(position))
        blend = (1-cos((position-index)*pi))/2
        return start+points[index]+(points[index+1]-points[index])*blend
    return sample


@overload
def _shake_tween(getter, setter, duration: float, strength: float=3, vibrato: int=10,
                 randomness: float=90, ignore_z_axis: bool=True, fade_out: bool=True,
                 randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def _shake_tween(getter, setter, duration: float, strength: Vector3, vibrato: int=10,
                 randomness: float=90, fade_out: bool=True,
                 randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
def _shake_tween(getter, setter, duration, *args, **kwargs):
    if duration <= 0:
        return None
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
    strength = _vector(strength)
    if not vector and values.get("ignore_z_axis", True):
        strength.z = 0
    sample = _shake_sample(strength, values.get("vibrato", 10), values.get("randomness", 90),
                           values.get("fade_out", True), values.get("randomness_mode", ShakeRandomnessMode.FULL))
    return _ImpulseTween(getter, setter, duration, sample)


def _shake(target, name, duration, strength, vibrato, randomness, snapping, fade_out, randomness_mode):
    if duration <= 0:
        return None
    sample = _shake_sample(strength, vibrato, randomness, fade_out, randomness_mode)
    return _default_manager.add(_target_motion(target, name, duration, sample, snapping, _ImpulseTween))


@overload
def do_shake_position(target: Transform, duration: float, strength: float=1, vibrato: int=10,
                      randomness: float=90, snapping: bool=False, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def do_shake_position(target: Transform, duration: float, strength: Vector3, vibrato: int=10,
                      randomness: float=90, snapping: bool=False, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def do_shake_position(target: Camera, duration: float, strength: float=3, vibrato: int=10,
                      randomness: float=90, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def do_shake_position(target: Camera, duration: float, strength: Vector3, vibrato: int=10,
                      randomness: float=90, fade_out: bool=True,
                      randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@singledispatch
def do_shake_position(target, duration, strength=1.0, vibrato=10, randomness=90, snapping=False,
                      fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    return _shake(target, "local_position", duration, strength, vibrato, randomness, snapping, fade_out, randomness_mode)


@do_shake_position.register(Camera)
def _camera_shake_position(target, duration, strength=3.0, vibrato=10, randomness=90,
                           fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    if duration <= 0:
        return None
    if type(strength) in (int, float):
        strength = Vector3(strength, strength, 0)
    elif not isinstance(strength, Vector3):
        raise TypeError("strength must be float or Vector3")
    displacement = _shake_sample(strength, vibrato, randomness, fade_out, randomness_mode)
    rotation = inverse = None

    def read():
        nonlocal rotation, inverse
        rotation = target.transform.local_rotation
        inverse = quatf.inverse(rotation)
        return target.transform.local_position

    def sample(start, progress, relative):
        offset = displacement(Vector3(0, 0, 0), progress, relative)
        rotated = rotation*quatf(*offset, 0)*inverse
        return start+Vector3(rotated.x, rotated.y, rotated.z)

    return _default_manager.add(_ImpulseTween(read, lambda value: setattr(target.transform, "local_position", value),
                                              duration, sample)).set_target(target)


def do_shake_rotation(target, duration, strength=90.0, vibrato=10, randomness=90,
                      fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    transform = target.transform if isinstance(target, Camera) else target
    tween = _shake(transform, "local_euler_angles", duration, strength, vibrato, randomness,
                   False, fade_out, randomness_mode)
    return None if tween is None else tween.set_target(target)


def do_shake_scale(target, duration, strength=1.0, vibrato=10, randomness=90,
                   fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    return _shake(target, "local_scale", duration, strength, vibrato, randomness, False, fade_out, randomness_mode)


def _blendable(target, name, by_value, duration, snapping=False):
    applied = Vector3(0, 0, 0)
    def write(displacement):
        nonlocal applied
        setattr(target, name, getattr(target, name)+displacement-applied)
        applied = displacement
    return _default_manager.to(lambda: Vector3(0, 0, 0), write, _vector(by_value), duration).set_options(snapping).set_target(target)


def do_blendable_move_by(target, by_value, duration, snapping=False): return _blendable(target, "position", by_value, duration, snapping)
def do_blendable_local_move_by(target, by_value, duration, snapping=False): return _blendable(target, "local_position", by_value, duration, snapping)
def do_blendable_scale_by(target, by_value, duration): return _blendable(target, "local_scale", by_value, duration)


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


def do_blendable_rotate_by(target, by_value, duration, mode=RotateMode.FAST):
    return _blendable_rotation(target, "rotation", by_value, duration, mode)


def do_blendable_local_rotate_by(target, by_value, duration, mode=RotateMode.FAST):
    return _blendable_rotation(target, "local_rotation", by_value, duration, mode)


def do_blendable_punch_rotation(target, punch: Vector3, duration: float, vibrato: int=10, elasticity: float=1):
    writer = _rotation_writer(target, "local_rotation", RotateMode.LOCAL_AXIS_ADD)
    tween = _punch_tween(lambda: Vector3(0, 0, 0), writer, punch, duration, vibrato, elasticity)
    return None if tween is None else _default_manager.add(tween).set_target(target)


def do_spiral(target, duration, axis=None, mode=SpiralMode.EXPAND, speed=1.0, frequency=10.0, depth=0.0, snapping=False):
    axis = Vector3(0, 0, 1) if axis is None else _vector(axis)
    if axis.sqr_magnitude == 0:
        raise ValueError("Spiral axis must be nonzero")
    axis = axis.normalized
    if not isinstance(mode, SpiralMode):
        raise TypeError("mode must be SpiralMode")
    reference = Vector3(0, 1, 0) if abs(axis.y) < 0.9 else Vector3(1, 0, 0)
    horizontal = Vector3.cross(reference, axis).normalized
    vertical = Vector3.cross(axis, horizontal)
    def sample(start, progress, relative):
        elapsed = progress*duration*speed
        radius = elapsed if mode == SpiralMode.EXPAND else duration*speed*(1-abs(2*progress-1))
        angle = elapsed*frequency
        return start+(horizontal*cos(angle)+vertical*sin(angle))*radius+axis*(depth*progress)
    name = "position" if isinstance(target, Rigidbody) else "local_position"
    return _default_manager.add(_target_motion(target, name, duration, sample, snapping))
