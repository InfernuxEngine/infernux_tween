from enum import Enum

from infernux.lib import quatf

from .core import DOTween, LoopType, Tweener, UpdateType


class RotateMode(str, Enum):
    Fast = "Fast"
    FastBeyond360 = "FastBeyond360"


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

    def SetLoops(self, loops, loop_type=LoopType.Restart):
        if LoopType(loop_type) == LoopType.Incremental:
            raise ValueError("Use Euler rotation for incremental turns")
        return super().SetLoops(loops, loop_type)


def DORotateQuaternion(target, to, duration):
    from infernux.components.builtin import Rigidbody
    setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
    tween = DOTween.add(QuaternionTweener(lambda: target.rotation, setter, to, duration)).SetTarget(target)
    return tween.SetUpdate(UpdateType.Fixed) if isinstance(target, Rigidbody) else tween


def DOLocalRotateQuaternion(target, to, duration):
    return DOTween.add(QuaternionTweener(lambda: target.local_rotation,
                       lambda value: setattr(target, "local_rotation", value), to, duration)).SetTarget(target)
