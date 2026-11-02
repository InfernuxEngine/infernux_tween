"""Typed animation shortcuts for native scene and UI components."""

from dataclasses import dataclass
from functools import singledispatch, partial
from math import isnan
from typing import overload

from infernux.components.builtin import AudioSource, Camera, Light, LineRenderer, TrailRenderer, Rigidbody, SpriteRenderer
from infernux.core.material import Material
from infernux.screen import Rect
from infernux.graph.ramp import Gradient
from infernux.lib import Transform, Vector2, Vector3, quatf, vec4f
from infernux.ui import InxUIScreenComponent, UIButton, UIGroup, UIImage, UILayoutElement, UISlider, UIText

from .core import _bind_arguments, _ColorTweener, _default_manager, _StartupDeclined, AxisConstraint, Tween, Tweener
from .ease import Ease
from .color import Color2
from infernux.lib._Infernux import _LiveColor2TweenSnapshot
from .motion import ShakeRandomnessMode, _jump, _punch_tween, _shake_offsets, _impulse_tween
from .circle import CirclePlugin
from .path import twn_path, twn_local_path
from .rotation import twn_rotate_quaternion, twn_local_rotate_quaternion, EulerTweener, RotateMode
from .motion import (twn_blendable_local_move_by, twn_blendable_move_by, twn_blendable_scale_by,
                     twn_blendable_rotate_by, twn_blendable_local_rotate_by, twn_spiral,
                     twn_jump, twn_local_jump, twn_punch_position, twn_punch_rotation, twn_punch_scale,
                     twn_shake_position, twn_shake_rotation, twn_shake_scale)
from .string import ScrambleMode, StringTweener


def _vector(value):
    return value if isinstance(value, Vector3) else Vector3(*value)


def _property(target, name, end_value, duration):
    return _default_manager.to(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                      end_value, duration).set_target(target)


def _move(target, name, end_value, duration, snapping=False):
    end = _vector(end_value)
    setter = lambda value: setattr(target, name, value)
    if isinstance(target, Rigidbody):
        if name != "position":
            raise TypeError("Rigidbody motion uses world-space position")
        setter = target.move_position
    elif not isinstance(target, Transform):
        raise TypeError("Motion shortcuts require a Transform or Rigidbody")
    tween = _default_manager.to(lambda: getattr(target, name), setter, end, duration).set_options(snapping).set_target(target)
    return tween


def _axis(target, name, axis, end_value, duration, snapping=False):
    getter = lambda: getattr(target, name)
    write = lambda value: setattr(target, name, value)
    if isinstance(target, Rigidbody):
        if name != "position":
            raise TypeError("Rigidbody motion uses world-space position")
        write = target.move_position

    constraint = AxisConstraint(2 << axis)
    tween = _default_manager.to_axis(getter, write, end_value, duration, constraint).set_options(
        constraint, snapping).set_target(target)
    return tween


def twn_move(target: Transform|Rigidbody, end_value: Vector3, duration: float, snapping: bool=False):
    return _move(target, "position", end_value, duration, snapping)


def twn_local_move(target: Transform, end_value: Vector3, duration: float, snapping: bool=False):
    return _move(target, "local_position", end_value, duration, snapping)


@overload
def twn_scale(target: Transform, end_value: Vector3, duration: float): ...
@overload
def twn_scale(target: Transform, end_value: float, duration: float): ...
def twn_scale(target, end_value, duration):
    if not isinstance(target, Transform):
        raise TypeError("twn_scale requires a Transform")
    end = Vector3(end_value, end_value, end_value) if isinstance(end_value, (int, float)) else _vector(end_value)
    return _property(target, "local_scale", end, duration)


def twn_rotate(target: Transform|Rigidbody, end_value: Vector3, duration: float, mode: RotateMode=RotateMode.FAST):
    setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
    tween = EulerTweener(lambda: target.rotation, setter, _vector(end_value), duration, mode).set_target(target)
    return _default_manager.add(tween)


def twn_local_rotate(target: Transform, end_value: Vector3, duration: float, mode: RotateMode=RotateMode.FAST):
    return _default_manager.add(EulerTweener(lambda: target.local_rotation,
        lambda value: setattr(target, "local_rotation", value), _vector(end_value), duration, mode)).set_target(target)


class _LookAtTweener(EulerTweener):
    def __init__(self, target, towards, duration, axis_constraint, up, dynamic=False):
        if not isinstance(axis_constraint, AxisConstraint):
            raise TypeError("axis_constraint must be AxisConstraint")
        setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
        super().__init__(lambda: target.rotation, setter, _vector(towards), duration)
        self._towards = Vector3(*_vector(towards)) if dynamic else Vector3()
        self._up = Vector3(0, 1, 0) if up is None else Vector3(*_vector(up))
        self._constraint, self._dynamic = axis_constraint, dynamic

    def _ensure_initialized(self):
        if not self._initialized and not isinstance(self.target, Transform):
            # Special startup runs before getter conversion/change setup. Its
            # false result retains zero Euler storage and the requested point.
            self._initialized = self._euler = True
            self._start, self._delta = Vector3(), Vector3()
            self._integer = self._sequence_value = False
            self._value_type = Vector3
            self._compile_numeric_value()
            raise _StartupDeclined()
        return super()._ensure_initialized()

    def _look_end(self, point):
        direction = point - self.target.position
        if self._constraint in (AxisConstraint.X, AxisConstraint.Y, AxisConstraint.Z):
            direction[(AxisConstraint.X, AxisConstraint.Y, AxisConstraint.Z).index(self._constraint)] = 0
        return quatf.look_rotation(direction, self._up).euler_angles

    def _capture_values(self):
        self._end = self._look_end(self._end)
        return super()._capture_values()

def twn_look_at(target: Transform|Rigidbody, towards: Vector3, duration: float,
               axis_constraint: AxisConstraint=AxisConstraint.NONE, up: Vector3|None=None):
    tween = _LookAtTweener(target, towards, duration, axis_constraint, up).set_target(target)
    return _default_manager.add(tween)


def twn_dynamic_look_at(target: Transform, towards: Vector3, duration: float,
                       axis_constraint: AxisConstraint=AxisConstraint.NONE, up: Vector3|None=None):
    if not isinstance(target, Transform):
        raise TypeError("twn_dynamic_look_at requires a Transform")
    return _default_manager.add(_LookAtTweener(target, towards, duration, axis_constraint, up, True)).set_target(target)


class _Color2Tweener(Tweener):
    @staticmethod
    def _copy_argument(value):
        return value.__copy__()

    def __init__(self, getter, setter, end_value, duration):
        super().__init__(getter, setter, self._copy_argument(end_value), duration)

    def _compile_numeric_value(self):
        self._numeric_value = _LiveColor2TweenSnapshot(self._start._native_pair, self._delta._native_pair)
        self._bind_numeric_sampler()

    def _distance(self):
        return 1.0

    def _bind_numeric_sampler(self):
        super()._bind_numeric_sampler()
        if self._numeric_value is None:
            return
        if self._numeric_ease is None:
            self._sample_numeric = partial(self._numeric_value.sample_custom, self._ease)
            self._sample_numeric_nested = self._sample_numeric


@overload
def twn_color(target: UIText|UIImage|UIButton|SpriteRenderer|Camera|Light, end_value: list[float], duration: float): ...
@overload
def twn_color(target: Material, end_value: list[float], duration: float): ...
@overload
def twn_color(target: Material, end_value: list[float], property: str, duration: float): ...
@overload
def twn_color(target: Material, end_value: list[float], property_id: int, duration: float): ...
@overload
def twn_color(target: LineRenderer, start_value: Color2, end_value: Color2, duration: float): ...
def twn_color(target, *args, **kwargs):
    return _color(target, *args, **kwargs)


@singledispatch
def _color(target, *args, **kwargs):
    raise TypeError(f"twn_color does not support {type(target).__name__}")


@_color.register(UIText)
@_color.register(UIImage)
def _ui_color(target, end_value, duration):
    return _property(target, "color", list(end_value), duration)


@_color.register(UIButton)
def _button_color(target, end_value, duration):
    return _property(target, "background_color", list(end_value), duration)


@_color.register(SpriteRenderer)
def _sprite_color(target, end_value, duration):
    return _property(target, "sprite_color", list(end_value), duration)


@_color.register(Camera)
def _camera_color(target, end_value, duration):
    return _property(target, "background_color", list(end_value), duration)


@_color.register(Light)
def _light_color(target, end_value, duration):
    return _property(target, "color", [end_value[i] for i in range(3)]+[target.color[3]], duration)


@_color.register(Material)
def _material_color(target, end_value, *args, **kwargs):
    property, duration = _material_arguments(args, kwargs)
    if not target.has_property(property):
        return None
    return _default_manager.to(lambda: target.get_color(property), lambda value: target.set_color(property, *value),
                      list(end_value), duration).set_target(target)


@_color.register(LineRenderer)
def _line_color(target, start_value, end_value, duration):
    if not isinstance(start_value, Color2) or not isinstance(end_value, Color2):
        raise TypeError("LineRenderer colors must be Color2")
    def write(value):
        if isinstance(value, Color2):
            target.start_color, target.end_color = value.ca, value.cb
        else:
            target.start_color, target.end_color = value[:4], value[4:]
    start_value = start_value.__copy__()
    def read():
        return start_value.__copy__()
    return _default_manager.add(_default_manager._new(
        _Color2Tweener, read, write, end_value, duration)).set_target(target)


def _material_arguments(args, kwargs, default="baseColor"):
    if (len(args) == 2 or 'property' in kwargs or 'property_id' in kwargs
            or args and ('duration' in kwargs or isinstance(args[0], str))):
        key = 'property_id' if 'property_id' in kwargs else 'property'
        property, duration = _bind_arguments((key, 'duration'), args, kwargs)
    else:
        duration, = _bind_arguments(('duration',), args, kwargs)
        property = default
    return Material.property_name(property), duration


class _BlendableColorTween(_ColorTweener):
    def __init__(self, getter, setter, end_value, duration):
        start = list(getter())
        self._applied = [0.0]*4

        def write(offset):
            setter([current+value-previous for current, value, previous
                    in zip(getter(), offset, self._applied, strict=True)])
            self._applied = list(offset)

        super().__init__(lambda: list(self._applied), write,
                         [end-current for current, end in zip(start, end_value, strict=True)], duration)


def _blendable_color_property(target, name, end_value, duration):
    return _default_manager.add(_BlendableColorTween(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                                           list(end_value), duration)).set_target(target)


@overload
def twn_blendable_color(target: UIText|UIImage|UIButton|SpriteRenderer|Camera|Light, end_value: list[float], duration: float): ...
@overload
def twn_blendable_color(target: Material, end_value: list[float], duration: float): ...
@overload
def twn_blendable_color(target: Material, end_value: list[float], property: str, duration: float): ...
@overload
def twn_blendable_color(target: Material, end_value: list[float], property_id: int, duration: float): ...
def twn_blendable_color(target, *args, **kwargs):
    return _blendable_color(target, *args, **kwargs)


@singledispatch
def _blendable_color(target, *args, **kwargs):
    raise TypeError(f"twn_blendable_color does not support {type(target).__name__}")


@_blendable_color.register(UIText)
@_blendable_color.register(UIImage)
@_blendable_color.register(Camera)
def _blendable_ui_color(target, end_value, duration):
    return _blendable_color_property(target, "background_color" if isinstance(target, Camera) else "color", end_value, duration)


@_blendable_color.register(UIButton)
def _blendable_button_color(target, end_value, duration):
    return _blendable_color_property(target, "background_color", end_value, duration)


@_blendable_color.register(SpriteRenderer)
def _blendable_sprite_color(target, end_value, duration):
    return _blendable_color_property(target, "sprite_color", end_value, duration)


@_blendable_color.register(Light)
def _blendable_light_color(target, end_value, duration):
    return _blendable_color_property(target, "color", [end_value[i] for i in range(3)]+[target.color[3]], duration)


@_blendable_color.register(Material)
def _blendable_material_color(target, end_value, *args, **kwargs):
    property, duration = _material_arguments(args, kwargs)
    if not target.has_property(property):
        return None
    return _default_manager.add(_BlendableColorTween(lambda: target.get_color(property), lambda value: target.set_color(property, *value),
                                           list(end_value), duration)).set_target(target)


@overload
def twn_fade(target: InxUIScreenComponent|AudioSource|SpriteRenderer, end_value: float, duration: float): ...
@overload
def twn_fade(target: Material, end_value: float, duration: float): ...
@overload
def twn_fade(target: Material, end_value: float, property: str, duration: float): ...
@overload
def twn_fade(target: Material, end_value: float, property_id: int, duration: float): ...
def twn_fade(target, *args, **kwargs):
    return _fade(target, *args, **kwargs)


@singledispatch
def _fade(target, *args, **kwargs):
    raise TypeError(f"twn_fade does not support {type(target).__name__}")


@_fade.register(InxUIScreenComponent)
def _ui_fade(target, end_value, duration):
    return _property(target, "opacity", end_value, duration)


@_fade.register(UIText)
@_fade.register(UIImage)
@_fade.register(UIButton)
def _graphic_fade(target, end_value, duration):
    name = "background_color" if isinstance(target, UIButton) else "color"
    return _default_manager.to_alpha(lambda: list(getattr(target, name)), lambda value: setattr(target, name, list(value)),
                                    end_value, duration).set_target(target)


@_fade.register(UIGroup)
def _group_fade(target, end_value, duration):
    return _property(target, "alpha", end_value, duration)


@_fade.register(AudioSource)
def _audio_fade(target, end_value, duration):
    return _property(target, "volume", end_value, duration)


@_fade.register(SpriteRenderer)
def _sprite_fade(target, end_value, duration):
    return _default_manager.to_alpha(lambda: list(target.sprite_color), lambda value: setattr(target, "sprite_color", list(value)),
                                    end_value, duration).set_target(target)


@_fade.register(Material)
def _material_fade(target, end_value, *args, **kwargs):
    property, duration = _material_arguments(args, kwargs)
    if not target.has_property(property):
        return None
    return _default_manager.to_alpha(lambda: list(target.get_color(property)), lambda value: target.set_color(property, *value),
                                    end_value, duration).set_target(target)


def _gradient_color(target, gradient, duration, getter, setter):
    if not isinstance(gradient, Gradient):
        raise TypeError("gradient must be Gradient")
    sequence = _default_manager.sequence().set_target(target)

    def write(color):
        setter([*color[:3], getter()[3]])

    for index, key in enumerate(gradient.keys):
        color = list(key.color)
        if index == 0 and key.time == 0:
            write(color)
            continue
        span = (duration-sequence.duration(False) if index == len(gradient.keys)-1 else
                duration*(key.time-(gradient.keys[index-1].time if index else 0)))
        sequence.append(_default_manager.to(getter, write, color, span).set_ease(Ease.LINEAR))
    return sequence


@overload
def twn_gradient_color(target: UIImage|SpriteRenderer, gradient: Gradient, duration: float): ...
@overload
def twn_gradient_color(target: Material, gradient: Gradient, duration: float): ...
@overload
def twn_gradient_color(target: Material, gradient: Gradient, property: str, duration: float): ...
def twn_gradient_color(target, *args, **kwargs):
    return _gradient(target, *args, **kwargs)


@singledispatch
def _gradient(target, *args, **kwargs):
    raise TypeError(f"twn_gradient_color does not support {type(target).__name__}")


@_gradient.register(UIImage)
def _image_gradient(target, gradient, duration):
    return _gradient_color(target, gradient, duration, lambda: list(target.color),
                           lambda value: setattr(target, "color", value))


@_gradient.register(SpriteRenderer)
def _sprite_gradient(target, gradient, duration):
    return _gradient_color(target, gradient, duration, lambda: list(target.sprite_color),
                           lambda value: setattr(target, "sprite_color", value))


@_gradient.register(Material)
def _material_gradient(target, gradient, *args, **kwargs):
    property, duration = _material_arguments(args, kwargs)
    if not target.has_property(property):
        return None
    return _gradient_color(target, gradient, duration, lambda: list(target.get_color(property)),
                           lambda value: target.set_color(property, *value))


@overload
def twn_offset(target: Material, end_value: Vector2, duration: float): ...
@overload
def twn_offset(target: Material, end_value: Vector2, property: str, duration: float): ...
@overload
def twn_offset(target: Material, end_value: Vector2, property_id: int, duration: float): ...
def twn_offset(target, end_value, *args, **kwargs):
    return _texture_transform_tween(target, end_value, args, kwargs, "offset")


@overload
def twn_tiling(target: Material, end_value: Vector2, duration: float): ...
@overload
def twn_tiling(target: Material, end_value: Vector2, property: str, duration: float): ...
@overload
def twn_tiling(target: Material, end_value: Vector2, property_id: int, duration: float): ...
def twn_tiling(target, end_value, *args, **kwargs):
    return _texture_transform_tween(target, end_value, args, kwargs, "scale")


def _texture_transform_tween(target, end_value, args, kwargs, channel):
    if not isinstance(target, Material):
        raise TypeError("texture transforms require a Material")
    name, duration = _material_arguments(args, kwargs, default="texSampler")
    if not target.has_property(name):
        return None
    getter = getattr(target, "get_texture_" + channel)
    setter = getattr(target, "set_texture_" + channel)
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _default_manager.to(lambda: getter(name), lambda value: setter(name, value), end, duration).set_target(target)


def twn_aspect(target: Camera, end_value: float, duration: float):
    """Animate the camera's projection aspect independently of viewport resizing."""
    if not isinstance(target, Camera):
        raise TypeError("twn_aspect requires a Camera")
    return _property(target, "aspect_ratio", end_value, duration)


def twn_rect(target: Camera, end_value: Rect, duration: float):
    if not isinstance(target, Camera) or not isinstance(end_value, Rect):
        raise TypeError("twn_rect requires a Camera and Rect")
    return _property(target, "rect", end_value, duration)


def twn_pixel_rect(target: Camera, end_value: Rect, duration: float):
    if not isinstance(target, Camera) or not isinstance(end_value, Rect):
        raise TypeError("twn_pixel_rect requires a Camera and Rect")
    return _property(target, "pixel_rect", end_value, duration)


def twn_value(target: UISlider, end_value: float, duration: float, snapping: bool=False):
    return _default_manager.to(lambda: target.value, target.set_value, end_value,
                               duration).set_options(snapping).set_target(target)


def twn_normalized_pos(target, end_value: Vector2, duration: float, snapping: bool=False):
    """Animate a scrolling target's writable Vector2 normalized_position."""
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _property(target, "normalized_position", end, duration).set_options(snapping)


def twn_horizontal_normalized_pos(target, end_value: float, duration: float, snapping: bool=False):
    """Animate horizontal_normalized_position, leaving the other axis to its owner."""
    return _property(target, "horizontal_normalized_position", float(end_value), duration).set_options(snapping)


def twn_vertical_normalized_pos(target, end_value: float, duration: float, snapping: bool=False):
    """Animate vertical_normalized_position, leaving the other axis to its owner."""
    return _property(target, "vertical_normalized_position", float(end_value), duration).set_options(snapping)


def twn_set_float(target, float_name: str, end_value: float, duration: float):
    """Animate an exposed parameter through get_float(name) / set_float(name, value).

    get_float must return a numeric value. Parameter exposure, units and any
    audio-thread publication belong to the target, not the tween scheduler.
    """
    read, write = target.get_float, target.set_float
    return _default_manager.to(lambda: float(read(float_name)), lambda value: write(float_name, value),
                               float(end_value), duration).set_target(target)


def twn_fill_amount(target: UIImage, end_value: float, duration: float):
    if not isinstance(target, UIImage):
        raise TypeError("twn_fill_amount requires UIImage")
    end_value=float(end_value)
    if isnan(end_value):
        raise ValueError("Image fill amount must not be NaN")
    return _property(target, "fill_amount", max(0.0,min(1.0,end_value)), duration)


def twn_pivot(target: InxUIScreenComponent, end_value: Vector2, duration: float):
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _default_manager.to(lambda: Vector2(*target.pivot), lambda value: setattr(target, 'pivot', value),
                               end, duration).set_target(target)


def twn_pivot_x(target: InxUIScreenComponent, end_value: float, duration: float):
    return twn_pivot(target, Vector2(end_value, 0), duration).set_options(AxisConstraint.X)


def twn_pivot_y(target: InxUIScreenComponent, end_value: float, duration: float):
    return twn_pivot(target, Vector2(0, end_value), duration).set_options(AxisConstraint.Y)


def twn_size_delta(target: InxUIScreenComponent, end_value: Vector2, duration: float, snapping: bool=False):
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _property(target, 'size_delta', end, duration).set_options(snapping)


def twn_anchor_min(target: InxUIScreenComponent, end_value: Vector2, duration: float, snapping: bool=False):
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _property(target, 'anchor_min', end, duration).set_options(snapping)


def twn_anchor_max(target: InxUIScreenComponent, end_value: Vector2, duration: float, snapping: bool=False):
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _property(target, 'anchor_max', end, duration).set_options(snapping)


def twn_anchor_pos(target: InxUIScreenComponent, end_value: Vector2, duration: float, snapping: bool=False):
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _property(target, 'anchored_position', end, duration).set_options(snapping)


def twn_anchor_pos_x(target: InxUIScreenComponent, end_value: float, duration: float, snapping: bool=False):
    return twn_anchor_pos(target, Vector2(end_value, 0), duration).set_options(AxisConstraint.X, snapping)


def twn_anchor_pos_y(target: InxUIScreenComponent, end_value: float, duration: float, snapping: bool=False):
    return twn_anchor_pos(target, Vector2(0, end_value), duration).set_options(AxisConstraint.Y, snapping)


def twn_anchor_pos3d(target: InxUIScreenComponent, end_value: Vector3, duration: float, snapping: bool=False):
    return _property(target, 'anchored_position3d', _vector(end_value), duration).set_options(snapping)


def twn_anchor_pos3d_x(target: InxUIScreenComponent, end_value: float, duration: float, snapping: bool=False):
    return twn_anchor_pos3d(target, Vector3(end_value, 0, 0), duration).set_options(AxisConstraint.X, snapping)


def twn_anchor_pos3d_y(target: InxUIScreenComponent, end_value: float, duration: float, snapping: bool=False):
    return twn_anchor_pos3d(target, Vector3(0, end_value, 0), duration).set_options(AxisConstraint.Y, snapping)


def twn_anchor_pos3d_z(target: InxUIScreenComponent, end_value: float, duration: float, snapping: bool=False):
    return twn_anchor_pos3d(target, Vector3(0, 0, end_value), duration).set_options(AxisConstraint.Z, snapping)


def twn_jump_anchor_pos(target: InxUIScreenComponent, end_value: Vector2, jump_power: float,
                        num_jumps: int, duration: float, snapping: bool=False):
    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _jump(target, 'anchored_position', end, jump_power, num_jumps, duration, snapping)


def twn_punch_anchor_pos(target: InxUIScreenComponent, punch: Vector2, duration: float,
                         vibrato: int=10, elasticity: float=1., snapping: bool=False):
    if duration <= 0:
        return None
    layout = target.rect_transform
    direction = Vector3(punch[0], punch[1], 0)
    tween = _punch_tween(lambda: layout._planar_position, lambda value: setattr(layout, '_planar_position', value),
                         direction, duration, vibrato, elasticity)
    return _default_manager.add(tween).set_options(snapping).set_target(target)


@overload
def twn_shake_anchor_pos(target: InxUIScreenComponent, duration: float, strength: float=100., vibrato: int=10,
                         randomness: float=90., snapping: bool=False, fade_out: bool=True,
                         randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
@overload
def twn_shake_anchor_pos(target: InxUIScreenComponent, duration: float, strength: Vector2, vibrato: int=10,
                         randomness: float=90., snapping: bool=False, fade_out: bool=True,
                         randomness_mode: ShakeRandomnessMode=ShakeRandomnessMode.FULL): ...
def twn_shake_anchor_pos(target, duration, strength=100., vibrato=10, randomness=90., snapping=False,
                         fade_out=True, randomness_mode=ShakeRandomnessMode.FULL):
    if duration <= 0:
        return None
    if isinstance(strength, Vector2):
        strength = Vector3(strength.x, strength.y, 0)
    offsets, durations = _shake_offsets(duration, strength, vibrato, randomness, fade_out, randomness_mode, True)
    layout = target.rect_transform
    tween = _impulse_tween(lambda: layout._planar_position, lambda value: setattr(layout, '_planar_position', value),
                           offsets, durations, 'shake')
    return _default_manager.add(tween).set_options(snapping).set_target(target)


def twn_shape_circle(target: InxUIScreenComponent, center: Vector2, end_value_degrees: float,
                      duration: float, relative_center: bool=False, snapping: bool=False):
    point = center if isinstance(center, Vector2) else Vector2(*center)
    return _default_manager.to(CirclePlugin.get(), lambda: target.anchored_position,
        lambda value: setattr(target, 'anchored_position', value), point, duration).set_options(
            end_value_degrees, relative_center, snapping).set_target(target)


def _layout_size(target, prefix, end_value, duration, snapping):
    if not isinstance(target, UILayoutElement):
        raise TypeError("Layout size shortcuts require a UILayoutElement")
    width, height = prefix + "_width", prefix + "_height"

    def write(value):
        setattr(target, width, value.x)
        setattr(target, height, value.y)

    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _default_manager.to(lambda: Vector2(getattr(target, width), getattr(target, height)),
                               write, end, duration).set_options(snapping).set_target(target)


def twn_min_size(target: UILayoutElement, end_value: Vector2, duration: float, snapping: bool=False):
    return _layout_size(target, "min", end_value, duration, snapping)


def twn_preferred_size(target: UILayoutElement, end_value: Vector2, duration: float, snapping: bool=False):
    return _layout_size(target, "preferred", end_value, duration, snapping)


def twn_flexible_size(target: UILayoutElement, end_value: Vector2, duration: float, snapping: bool=False):
    return _layout_size(target, "flexible", end_value, duration, snapping)


def twn_text(target: UIText, end_value: str, duration: float, rich_text_enabled: bool=True,
            scramble_mode: ScrambleMode=ScrambleMode.NONE, scramble_chars: str|None=None):
    if not isinstance(end_value, str):
        raise TypeError("end_value must be str")
    tween = StringTweener(lambda: target.text, lambda value: setattr(target, "text", value), end_value, duration)
    tween.set_options(rich_text_enabled, scramble_mode, scramble_chars)
    target.rich_text = rich_text_enabled
    return _default_manager.add(tween).set_target(target)


@dataclass(frozen=True)
class CultureInfo:
    number_group_separator: str = ","
    number_group_sizes: tuple[int, ...] = (3,)

    def __post_init__(self):
        sizes = tuple(self.number_group_sizes)
        if not isinstance(self.number_group_separator, str):
            raise TypeError("number_group_separator must be str")
        if any(type(size) is not int or not 0 <= size <= 9 or size == 0 and i < len(sizes)-1
               for i, size in enumerate(sizes)):
            raise ValueError("number_group_sizes must be 1..9, with an optional final 0")
        object.__setattr__(self, "number_group_sizes", sizes)

    def format_integer(self, value: int) -> str:
        if not self.number_group_sizes:
            return str(value)
        digits, groups, index = str(abs(value)), [], 0
        while digits:
            size = self.number_group_sizes[min(index, len(self.number_group_sizes)-1)]
            if size == 0:
                groups.append(digits)
                break
            groups.append(digits[-size:])
            digits = digits[:-size]
            index += 1
        return ("-" if value < 0 else "") + self.number_group_separator.join(reversed(groups))


def twn_counter(target: UIText, from_value: int, end_value: int, duration: float,
               add_thousands_separator: bool=True, culture: CultureInfo|None=None):
    if type(from_value) is not int or type(end_value) is not int:
        raise TypeError("Counter values must be int")
    if culture is not None and not isinstance(culture, CultureInfo):
        raise TypeError("culture must be CultureInfo or None")
    formatter = (CultureInfo() if culture is None else culture).format_integer if add_thousands_separator else str
    def write(value):
        target.text = formatter(value)
    return _default_manager.to(lambda: from_value, write, end_value, duration).set_target(target)


def twn_max_visible_characters(target: UIText, end_value: int, duration: float):
    if type(end_value) is not int:
        raise TypeError("end_value must be int")
    if target.max_visible_characters < 0:
        target.max_visible_characters = 0
    return _property(target, "max_visible_characters", end_value, duration)


def twn_move_x(target: Transform|Rigidbody, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "position", 0, end_value, duration, snapping)


def twn_move_y(target: Transform|Rigidbody, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "position", 1, end_value, duration, snapping)


def twn_move_z(target: Transform|Rigidbody, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "position", 2, end_value, duration, snapping)


def twn_local_move_x(target: Transform, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "local_position", 0, end_value, duration, snapping)


def twn_local_move_y(target: Transform, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "local_position", 1, end_value, duration, snapping)


def twn_local_move_z(target: Transform, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "local_position", 2, end_value, duration, snapping)


def twn_scale_x(target: Transform, end_value: float, duration: float):
    return _axis(target, "local_scale", 0, end_value, duration)


def twn_scale_y(target: Transform, end_value: float, duration: float):
    return _axis(target, "local_scale", 1, end_value, duration)


def twn_scale_z(target: Transform, end_value: float, duration: float):
    return _axis(target, "local_scale", 2, end_value, duration)


def twn_pitch(target: AudioSource, end_value: float, duration: float):
    return _property(target, "pitch", end_value, duration)


def twn_intensity(target: Light, end_value: float, duration: float):
    return _property(target, "intensity", end_value, duration)


def twn_shadow_strength(target: Light, end_value: float, duration: float):
    return _property(target, "shadow_strength", end_value, duration)


def twn_field_of_view(target: Camera, end_value: float, duration: float):
    return _property(target, "field_of_view", end_value, duration)


def twn_ortho_size(target: Camera, end_value: float, duration: float):
    return _property(target, "orthographic_size", end_value, duration)


def twn_near_clip_plane(target: Camera, end_value: float, duration: float):
    return _property(target, "near_clip", end_value, duration)


def twn_far_clip_plane(target: Camera, end_value: float, duration: float):
    return _property(target, "far_clip", end_value, duration)


def twn_font_size(target: UIText, end_value: float, duration: float):
    return _property(target, "font_size", end_value, duration)


def twn_time_scale(target: Tween, end_value: float, duration: float):
    return _property(target, "time_scale", end_value, duration)


def twn_resize(target: TrailRenderer, to_start_width: float, to_end_width: float, duration: float):
    if not isinstance(target, TrailRenderer):
        raise TypeError("twn_resize requires a TrailRenderer")
    def write(value):
        target.start_width = value.x
        target.end_width = value.y
    return _default_manager.to(lambda: Vector2(target.start_width, target.end_width), write,
                               Vector2(to_start_width, to_end_width), duration).set_target(target)


def twn_time(target: TrailRenderer, end_value: float, duration: float):
    if not isinstance(target, TrailRenderer):
        raise TypeError("twn_time requires a TrailRenderer")
    return _property(target, "time", end_value, duration)


@overload
def twn_float(target: Material, end_value: float, property: str, duration: float): ...
@overload
def twn_float(target: Material, end_value: float, property_id: int, duration: float): ...
def twn_float(target: Material, end_value: float, *args, **kwargs):
    property, duration = _material_arguments(args, kwargs, default=None)
    if not target.has_property(property):
        return None
    return _default_manager.to(lambda: target.get_float(property), lambda value: target.set_float(property, value),
                      end_value, duration).set_target(target)


@overload
def twn_vector(target: Material, end_value: vec4f, property: str, duration: float): ...
@overload
def twn_vector(target: Material, end_value: vec4f, property_id: int, duration: float): ...
def twn_vector(target: Material, end_value: vec4f, *args, **kwargs):
    property, duration = _material_arguments(args, kwargs, default=None)
    if not target.has_property(property):
        return None
    end = end_value if isinstance(end_value, vec4f) else vec4f(*end_value)
    return _default_manager.to(lambda: vec4f(*target.get_vector4(property)), lambda value: target.set_vector4(property, *value),
                               end, duration).set_target(target)


def twn_complete(target: object, with_callbacks: bool=False): return _default_manager.complete(target, with_callbacks)


def twn_kill(target: object, complete: bool=False): return _default_manager.kill(target, complete)


def twn_flip(target: object): return _default_manager.flip(target)


def twn_goto(target: object, to: float, and_play: bool=False): return _default_manager.goto(target, to, and_play)


def twn_pause(target: object): return _default_manager.pause(target)


def twn_play(target: object): return _default_manager.play(target)


def twn_play_backwards(target: object): return _default_manager.play_backwards(target)


def twn_play_forward(target: object): return _default_manager.play_forward(target)


def twn_restart(target: object, include_delay: bool=True): return _default_manager.restart(target, include_delay)


def twn_rewind(target: object, include_delay: bool=True): return _default_manager.rewind(target, include_delay)


def twn_smooth_rewind(target: object): return _default_manager.smooth_rewind(target)


def twn_toggle_pause(target: object): return _default_manager.toggle_pause(target)
