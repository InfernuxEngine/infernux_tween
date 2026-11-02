"""Time mapping over the engine's authored AnimationCurve.

Owns no interpolation, key storage, or serialization format. The original
curve remains live; edits are visible to existing tweens.
"""
from infernux.graph.ramp import AnimationCurve
from infernux.lib import Vector3
from infernux.lib._Infernux import _cubic_bezier_point, _cubic_bezier_cloud, _append_cubic_bezier_cloud
from typing import overload


class CubicBezier:
    """Cubic segment utilities with uniform parameter sampling."""

    get_point_on_segment = staticmethod(_cubic_bezier_point)

    @staticmethod
    @overload
    def get_segment_point_cloud(start_point: Vector3, start_control_point: Vector3,
                                end_point: Vector3, end_control_point: Vector3,
                                resolution: int = 10) -> list[Vector3]: ...
    @staticmethod
    @overload
    def get_segment_point_cloud(add_to_list: list[Vector3], start_point: Vector3,
                                start_control_point: Vector3, end_point: Vector3,
                                end_control_point: Vector3, resolution: int = 10) -> None: ...
    @staticmethod
    def get_segment_point_cloud(*args, **kwargs):
        from .core import _bind_arguments
        append = 'add_to_list' in kwargs or args and isinstance(args[0], list)
        names = ('start_point', 'start_control_point', 'end_point', 'end_control_point', 'resolution')
        if append:
            names = ('add_to_list', *names)
        values = _bind_arguments(names, args, kwargs, {'resolution': 10})
        return (_append_cubic_bezier_cloud if append else _cubic_bezier_cloud)(*values)


class TweenCurve:
    CubicBezier = CubicBezier


class EaseCurve:
    def __init__(self, anim_curve: AnimationCurve):
        if not isinstance(anim_curve, AnimationCurve):
            raise TypeError("anim_curve must be an engine AnimationCurve")
        self._anim_curve = anim_curve
        self._state = None

    def _curve_state(self):
        revision = self._anim_curve.revision
        state = self._state
        if state is None or state[0] != revision:
            snapshot = self._anim_curve._native_snapshot()
            if not snapshot.length:
                raise IndexError("curve key index out of range")
            state = revision, snapshot, snapshot.last_time
            self._state = state
        return state

    def evaluate(self, time: float, duration: float, unused_overshoot: float, unused_period: float) -> float:
        _, snapshot, end = self._curve_state()
        return snapshot.evaluate_mapped(time, duration, end)

    def __call__(self, progress: float) -> float:
        return self.evaluate(progress, 1.0, 0.0, 0.0)

    def evaluate_many(self, times, duration: float = 1.0, unused_overshoot: float = 0.0,
                      unused_period: float = 0.0):
        """Infernux extension: one C++ batch; large jobs release the GIL."""
        _, snapshot, end = self._curve_state()
        return snapshot.evaluate_many(times, time_scale=end, time_divisor=duration)

    def evaluate_into(self, times, values, duration: float = 1.0, unused_overshoot: float = 0.0,
                      unused_period: float = 0.0) -> None:
        """Infernux extension: write to an existing contiguous float64 buffer."""
        _, snapshot, end = self._curve_state()
        snapshot.evaluate_into(times, values, time_scale=end, time_divisor=duration)
