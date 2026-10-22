"""Seekable procedural motion and additive displacement."""
from math import cos, pi, sin
from enum import Enum
import random

from infernux.components.builtin import Rigidbody
from infernux.lib import Vector3, quatf

from .core import DOTween, LoopType, Tween, UpdateType
from .ease import Ease, resolve_ease
from .rotation import RotateMode


class SpiralMode(str, Enum):
    Expand = "Expand"
    ExpandThenContract = "ExpandThenContract"


def _vector(value):
    return Vector3(value, value, value) if isinstance(value, (int, float)) else Vector3(*value)


class MotionTween(Tween):
    def __init__(self, target, name, duration, sample, snapping=False):
        super().__init__(duration)
        self.target, self._name, self._sample = target, name, sample
        self._snapping, self._start = snapping, None
        self._relative = False
        self._ease = resolve_ease(Ease.Linear)
        self._body = isinstance(target, Rigidbody)
        if self._body:
            if name != "position":
                raise TypeError("Rigidbody procedural motion uses world position")
            self.update_type = UpdateType.Fixed

    def SetEase(self, ease):
        self._ease = resolve_ease(ease)
        return self

    def ForceInit(self):
        if self._start is None:
            self._start = getattr(self.target, self._name)
        return super().ForceInit()

    def _set_relative(self, relative):
        self._relative = relative

    def SetLoops(self, loops, loop_type=LoopType.Restart):
        if LoopType(loop_type) == LoopType.Incremental:
            raise ValueError("Procedural motion supports restart and yoyo loops")
        return super().SetLoops(loops, loop_type)

    def _apply(self, progress, cycle, previous, callbacks):
        self.ForceInit()
        value = self._sample(self._start, self._ease(progress), self._relative)
        if self._snapping:
            value = Vector3(*(round(item) for item in value))
        if self._body:
            self.target.move_position(value)
        else:
            setattr(self.target, self._name, value)


def _jump(target, name, end_value, jump_power, num_jumps, duration, snapping):
    if int(num_jumps) != num_jumps or num_jumps < 1:
        raise ValueError("Jump count must be a positive integer")
    end = _vector(end_value)
    def sample(start, progress, relative):
        phase = (progress*num_jumps) % 1
        return start+(end if relative else end-start)*progress+Vector3(0, 4*jump_power*phase*(1-phase), 0)
    return DOTween.Sequence().Append(MotionTween(target, name, duration, sample, snapping)).SetTarget(target)


def DOJump(target, end_value, jump_power, num_jumps, duration, snapping=False):
    sequence = _jump(target, "position", end_value, jump_power, num_jumps, duration, snapping)
    return sequence.SetUpdate(UpdateType.Fixed) if isinstance(target, Rigidbody) else sequence


def DOLocalJump(target, end_value, jump_power, num_jumps, duration, snapping=False):
    return _jump(target, "local_position", end_value, jump_power, num_jumps, duration, snapping)


def _punch(target, name, punch, duration, vibrato=10, elasticity=1.0, snapping=False):
    if vibrato < 1 or not 0 <= elasticity <= 1:
        raise ValueError("Punch needs positive vibrato and elasticity in [0, 1]")
    strength = _vector(punch)
    def sample(start, progress, relative):
        wave = sin(progress*pi*2*vibrato)*(1-progress)**2
        return start+strength*(wave if wave >= 0 else wave*elasticity)
    return DOTween.add(MotionTween(target, name, duration, sample, snapping))


def DOPunchPosition(target, punch, duration, vibrato=10, elasticity=1.0, snapping=False):
    return _punch(target, "local_position", punch, duration, vibrato, elasticity, snapping)


def DOPunchRotation(target, punch, duration, vibrato=10, elasticity=1.0):
    return _punch(target, "local_euler_angles", punch, duration, vibrato, elasticity)


def DOPunchScale(target, punch, duration, vibrato=10, elasticity=1.0):
    return _punch(target, "local_scale", punch, duration, vibrato, elasticity)


def _shake(target, name, duration, strength, vibrato, randomness, snapping, fade_out, seed):
    if int(vibrato) != vibrato or vibrato < 1 or not 0 <= randomness <= 180:
        raise ValueError("Shake needs integer vibrato > 0 and randomness in [0, 180]")
    rng, strength = random.Random(seed), _vector(strength)
    points = [Vector3(0, 0, 0)]
    angle = 0.0
    for index in range(vibrato):
        angle += pi+rng.uniform(-randomness, randomness)*pi/180
        tilt = rng.uniform(-randomness, randomness)*pi/180
        fade = 1-index/vibrato if fade_out else 1
        points.append(Vector3(cos(angle)*cos(tilt)*strength.x,
                              sin(angle)*cos(tilt)*strength.y, sin(tilt)*strength.z)*fade)
    points.append(Vector3(0, 0, 0))
    def sample(start, progress, relative):
        position = min(1, max(0, progress))*(len(points)-1)
        index = min(len(points)-2, int(position))
        blend = (1-cos((position-index)*pi))/2
        return start+points[index]+(points[index+1]-points[index])*blend
    return DOTween.add(MotionTween(target, name, duration, sample, snapping))


def DOShakePosition(target, duration, strength=1.0, vibrato=10, randomness=90, snapping=False, fade_out=True, *, seed=0):
    return _shake(target, "local_position", duration, strength, vibrato, randomness, snapping, fade_out, seed)


def DOShakeRotation(target, duration, strength=90.0, vibrato=10, randomness=90, fade_out=True, *, seed=0):
    return _shake(target, "local_euler_angles", duration, strength, vibrato, randomness, False, fade_out, seed)


def DOShakeScale(target, duration, strength=1.0, vibrato=10, randomness=90, fade_out=True, *, seed=0):
    return _shake(target, "local_scale", duration, strength, vibrato, randomness, False, fade_out, seed)


def _blendable(target, name, by, duration):
    applied = Vector3(0, 0, 0)
    def write(displacement):
        nonlocal applied
        setattr(target, name, getattr(target, name)+displacement-applied)
        applied = displacement
    return DOTween.To(lambda: Vector3(0, 0, 0), write, _vector(by), duration).SetTarget(target)


def DOBlendableMoveBy(target, by, duration): return _blendable(target, "position", by, duration)
def DOBlendableLocalMoveBy(target, by, duration): return _blendable(target, "local_position", by, duration)
def DOBlendableScaleBy(target, by, duration): return _blendable(target, "local_scale", by, duration)


def _blendable_rotation(target, name, by, duration, mode):
    by = _vector(by)
    if RotateMode(mode) == RotateMode.Fast:
        by = Vector3(*((value+180) % 360-180 for value in by))
    applied = quatf.identity()
    def write(value):
        nonlocal applied
        rotation = quatf.euler(*value)
        current = getattr(target, name)
        value = current*quatf.inverse(applied)*rotation if name == "local_rotation" else rotation*quatf.inverse(applied)*current
        setattr(target, name, value)
        applied = rotation
    return DOTween.To(lambda: Vector3(0, 0, 0), write, by, duration).SetTarget(target)


def DOBlendableRotateBy(target, by, duration, mode=RotateMode.FastBeyond360):
    return _blendable_rotation(target, "rotation", by, duration, mode)


def DOBlendableLocalRotateBy(target, by, duration, mode=RotateMode.FastBeyond360):
    return _blendable_rotation(target, "local_rotation", by, duration, mode)


def DOSpiral(target, duration, axis=None, mode=SpiralMode.Expand, speed=1.0, frequency=10.0, depth=0.0, snapping=False):
    axis = Vector3(0, 0, 1) if axis is None else _vector(axis)
    if axis.sqr_magnitude == 0:
        raise ValueError("Spiral axis must be nonzero")
    axis = axis.normalized
    mode = SpiralMode(mode)
    reference = Vector3(0, 1, 0) if abs(axis.y) < 0.9 else Vector3(1, 0, 0)
    horizontal = Vector3.cross(reference, axis).normalized
    vertical = Vector3.cross(axis, horizontal)
    def sample(start, progress, relative):
        elapsed = progress*duration*speed
        radius = elapsed if mode == SpiralMode.Expand else duration*speed*(1-abs(2*progress-1))
        angle = elapsed*frequency
        return start+(horizontal*cos(angle)+vertical*sin(angle))*radius+axis*(depth*progress)
    name = "position" if isinstance(target, Rigidbody) else "local_position"
    return DOTween.add(MotionTween(target, name, duration, sample, snapping))
