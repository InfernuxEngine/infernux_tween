"""Value sampling and delayed callbacks on the standard tween clock."""
import builtins
from typing import Callable, TypeVar, overload

from infernux.graph.ramp import AnimationCurve
from infernux.lib import Vector2, Vector3

from .core import _bind_arguments, _default_manager, _UNSET, Tween, Tweener
from .ease import Ease, resolve_ease

_Value = TypeVar('_Value', float, Vector3)


def _value(from_, to, duration, on_virtual_update):
    state = [from_]
    return _default_manager.to(lambda: state[0], lambda value: state.__setitem__(0, value), to, duration).on_update(
        lambda: on_virtual_update(state[0]))


def float(from_: builtins.float, to: builtins.float, duration: builtins.float,
          on_virtual_update: Callable[[builtins.float], None]) -> Tweener:
    return _value(builtins.float(from_), builtins.float(to), duration, on_virtual_update)


def int(from_: builtins.int, to: builtins.int, duration: builtins.float,
        on_virtual_update: Callable[[builtins.int], None]) -> Tweener:
    return _value(from_, to, duration, on_virtual_update)


def vector2(from_: Vector2, to: Vector2, duration: builtins.float,
            on_virtual_update: Callable[[Vector2], None]) -> Tweener:
    return _value(from_, to, duration, on_virtual_update)


def vector3(from_: Vector3, to: Vector3, duration: builtins.float,
            on_virtual_update: Callable[[Vector3], None]) -> Tweener:
    return _value(from_, to, duration, on_virtual_update)


def color(from_: list[builtins.float], to: list[builtins.float], duration: builtins.float,
          on_virtual_update: Callable[[list[builtins.float]], None]) -> Tweener:
    return _value(from_, to, duration, on_virtual_update)


@overload
def eased_value(from_: _Value, to: _Value, lifetime_percentage: builtins.float, ease_type: Ease) -> _Value: ...
@overload
def eased_value(from_: _Value, to: _Value, lifetime_percentage: builtins.float, ease_type: Ease, overshoot: builtins.float) -> _Value: ...
@overload
def eased_value(from_: _Value, to: _Value, lifetime_percentage: builtins.float, ease_type: Ease, amplitude: builtins.float, period: builtins.float) -> _Value: ...
@overload
def eased_value(from_: _Value, to: _Value, lifetime_percentage: builtins.float, ease_curve: AnimationCurve) -> _Value: ...
def eased_value(from_, to, lifetime_percentage, ease_type=_UNSET, *args, **kwargs):
    if 'ease_curve' in kwargs:
        if ease_type is not _UNSET:
            raise TypeError('provide one ease_type or ease_curve')
        ease_type = kwargs.pop('ease_curve')
    if not isinstance(ease_type, (Ease, AnimationCurve)) or isinstance(ease_type, AnimationCurve) and (args or kwargs):
        raise TypeError('use an Ease with its numeric options, or an AnimationCurve')
    amplitude, period = _default_manager.default_ease_overshoot_or_amplitude, _default_manager.default_ease_period
    if 'overshoot' in kwargs or len(args) == 1:
        amplitude, = _bind_arguments(('overshoot',), args, kwargs)
    elif args or kwargs:
        amplitude, period = _bind_arguments(('amplitude', 'period'), args, kwargs)
    return from_ + (to - from_) * resolve_ease(ease_type, amplitude, period)(lifetime_percentage)


def delayed_call(delay: builtins.float, callback: Callable[[], None], ignore_time_scale: bool=True) -> Tween:
    return (_default_manager.sequence().append_interval(delay).on_step_complete(callback)
            .set_update(ignore_time_scale).set_auto_kill(True))
