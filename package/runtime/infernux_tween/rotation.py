from infernux.lib import quatf

from .core import DOTween, LoopType, Tweener, UpdateType


class QuaternionTweener(Tweener):
    def _initialize(self):
        if self._start is not None:
            return
        start, end = self._getter().normalized, self._end.normalized
        if self._relative:
            end = start * end
        if self._from:
            start, end = end, start
        self._start, self._end = start, end
        if self._speed_based:
            self.duration = quatf.angle(start, end) / self.duration

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
