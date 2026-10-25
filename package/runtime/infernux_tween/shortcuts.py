"""Typed animation shortcuts for native scene and UI components."""

from dataclasses import dataclass
from functools import singledispatch
from typing import overload

from infernux.components.builtin import AudioSource, Camera, Light, LineRenderer, Rigidbody, SpriteRenderer
from infernux.core.material import Material
from infernux.graph.ramp import Gradient
from infernux.lib import Transform, Vector2, Vector3, quatf, vec4f
from infernux.ui import InxUIScreenComponent, UIButton, UIGroup, UIImage, UISlider, UIText

from .core import _bind_arguments, _ColorTweener, _default_manager, AxisConstraint, Tween, Tweener, UpdateType
from .ease import Ease
from .path import do_path, do_local_path
from .rotation import do_rotate_quaternion, do_local_rotate_quaternion, EulerTweener, RotateMode
from .motion import (do_blendable_local_move_by, do_blendable_move_by, do_blendable_scale_by,
                     do_blendable_rotate_by, do_blendable_local_rotate_by, do_spiral,
                     do_jump, do_local_jump, do_punch_position, do_punch_rotation, do_punch_scale,
                     do_shake_position, do_shake_rotation, do_shake_scale)
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
    if isinstance(target, Rigidbody):
        tween.set_update(UpdateType.FIXED)
    return tween


def _axis(target, name, axis, end_value, duration, snapping=False):
    getter = lambda: getattr(target, name)
    write = lambda value: setattr(target, name, value)
    if isinstance(target, Rigidbody):
        if name != "position":
            raise TypeError("Rigidbody motion uses world-space position")
        write = target.move_position
        start = [None]

        def getter():
            if start[0] is None:
                start[0] = target.position
            return start[0]

    constraint = AxisConstraint(2 << axis)
    tween = _default_manager.to_axis(getter, write, end_value, duration, constraint).set_options(
        constraint, snapping).set_target(target)
    if isinstance(target, Rigidbody):
        tween.set_update(UpdateType.FIXED)
    return tween


def do_move(target: Transform|Rigidbody, end_value: Vector3, duration: float, snapping: bool=False):
    return _move(target, "position", end_value, duration, snapping)


def do_local_move(target: Transform, end_value: Vector3, duration: float, snapping: bool=False):
    return _move(target, "local_position", end_value, duration, snapping)


@overload
def do_scale(target: Transform, end_value: Vector3, duration: float): ...
@overload
def do_scale(target: Transform, end_value: float, duration: float): ...
def do_scale(target, end_value, duration):
    if not isinstance(target, Transform):
        raise TypeError("do_scale requires a Transform")
    end = Vector3(end_value, end_value, end_value) if isinstance(end_value, (int, float)) else _vector(end_value)
    return _property(target, "local_scale", end, duration)


def do_rotate(target: Transform|Rigidbody, end_value: Vector3, duration: float, mode: RotateMode=RotateMode.FAST):
    setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
    tween = EulerTweener(lambda: target.rotation, setter, _vector(end_value), duration, mode).set_target(target)
    if isinstance(target, Rigidbody):
        tween.set_update(UpdateType.FIXED)
    return _default_manager.add(tween)


def do_local_rotate(target: Transform, end_value: Vector3, duration: float, mode: RotateMode=RotateMode.FAST):
    return _default_manager.add(EulerTweener(lambda: target.local_rotation,
        lambda value: setattr(target, "local_rotation", value), _vector(end_value), duration, mode)).set_target(target)


class _LookAtTweener(EulerTweener):
    def __init__(self, target, towards, duration, axis_constraint, up, dynamic=False):
        if not isinstance(axis_constraint, AxisConstraint):
            raise TypeError("axis_constraint must be AxisConstraint")
        self._look_target = target
        self._towards, self._up = _vector(towards), Vector3(0, 1, 0) if up is None else _vector(up)
        self._look_constraint, self._dynamic = axis_constraint, dynamic
        setter = target.move_rotation if isinstance(target, Rigidbody) else lambda value: setattr(target, "rotation", value)
        super().__init__(lambda: target.rotation, setter, Vector3(), duration)

    def _look_end(self):
        direction = self._towards - self._look_target.position
        if self._look_constraint in (AxisConstraint.X, AxisConstraint.Y, AxisConstraint.Z):
            direction[(AxisConstraint.X, AxisConstraint.Y, AxisConstraint.Z).index(self._look_constraint)] = 0
        return quatf.look_rotation(direction, self._up).euler_angles

    def _capture_values(self):
        self._end = self._look_end()
        return super()._capture_values()

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        if self._dynamic:
            self._set_values(self._start, self._look_end())
        super()._apply(progress, cycle, previous, callbacks)


def do_look_at(target: Transform|Rigidbody, towards: Vector3, duration: float,
               axis_constraint: AxisConstraint=AxisConstraint.NONE, up: Vector3|None=None):
    tween = _LookAtTweener(target, towards, duration, axis_constraint, up).set_target(target)
    if isinstance(target, Rigidbody):
        tween.set_update(UpdateType.FIXED)
    return _default_manager.add(tween)


def do_dynamic_look_at(target: Transform, towards: Vector3, duration: float,
                       axis_constraint: AxisConstraint=AxisConstraint.NONE, up: Vector3|None=None):
    if not isinstance(target, Transform):
        raise TypeError("do_dynamic_look_at requires a Transform")
    return _default_manager.add(_LookAtTweener(target, towards, duration, axis_constraint, up, True)).set_target(target)


@dataclass(frozen=True)
class Color2:
    ca: list[float]
    cb: list[float]

    def __iter__(self):
        return iter((*self.ca, *self.cb))

    def __add__(self, other):
        return Color2([a+b for a, b in zip(self.ca, other.ca, strict=True)],
                      [a+b for a, b in zip(self.cb, other.cb, strict=True)])

    def __sub__(self, other):
        return Color2([a-b for a, b in zip(self.ca, other.ca, strict=True)],
                      [a-b for a, b in zip(self.cb, other.cb, strict=True)])

    def __mul__(self, factor):
        return Color2([a*factor for a in self.ca], [a*factor for a in self.cb])


@overload
def do_color(target: UIText|UIImage|UIButton|SpriteRenderer|Camera|Light, end_value: list[float], duration: float): ...
@overload
def do_color(target: Material, end_value: list[float], duration: float): ...
@overload
def do_color(target: Material, end_value: list[float], property: str, duration: float): ...
@overload
def do_color(target: LineRenderer, start_value: Color2, end_value: Color2, duration: float): ...
def do_color(target, *args, **kwargs):
    return _color(target, *args, **kwargs)


@singledispatch
def _color(target, *args, **kwargs):
    raise TypeError(f"do_color does not support {type(target).__name__}")


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
        target.start_color, target.end_color = value.ca, value.cb
    return _default_manager.add(Tweener(lambda: start_value, write, end_value, duration)).set_target(target)


def _material_arguments(args, kwargs):
    if len(args) == 2 or 'property' in kwargs or args and isinstance(args[0], str):
        property, duration = _bind_arguments(('property', 'duration'), args, kwargs)
    else:
        duration, = _bind_arguments(('duration',), args, kwargs)
        property = "baseColor"
    if not isinstance(property, str):
        raise TypeError("Material property must be str")
    return property, duration


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
def do_blendable_color(target: UIText|UIImage|UIButton|SpriteRenderer|Camera|Light, end_value: list[float], duration: float): ...
@overload
def do_blendable_color(target: Material, end_value: list[float], duration: float): ...
@overload
def do_blendable_color(target: Material, end_value: list[float], property: str, duration: float): ...
def do_blendable_color(target, *args, **kwargs):
    return _blendable_color(target, *args, **kwargs)


@singledispatch
def _blendable_color(target, *args, **kwargs):
    raise TypeError(f"do_blendable_color does not support {type(target).__name__}")


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
def do_fade(target: InxUIScreenComponent|AudioSource|SpriteRenderer, end_value: float, duration: float): ...
@overload
def do_fade(target: Material, end_value: float, duration: float): ...
@overload
def do_fade(target: Material, end_value: float, property: str, duration: float): ...
def do_fade(target, *args, **kwargs):
    return _fade(target, *args, **kwargs)


@singledispatch
def _fade(target, *args, **kwargs):
    raise TypeError(f"do_fade does not support {type(target).__name__}")


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
def do_gradient_color(target: UIImage|SpriteRenderer, gradient: Gradient, duration: float): ...
@overload
def do_gradient_color(target: Material, gradient: Gradient, duration: float): ...
@overload
def do_gradient_color(target: Material, gradient: Gradient, property: str, duration: float): ...
def do_gradient_color(target, *args, **kwargs):
    return _gradient(target, *args, **kwargs)


@singledispatch
def _gradient(target, *args, **kwargs):
    raise TypeError(f"do_gradient_color does not support {type(target).__name__}")


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


def do_value(target: UISlider, end_value: float, duration: float, snapping: bool=False):
    return _default_manager.to(lambda: target.value, target.set_value, end_value,
                               duration).set_options(snapping).set_target(target)


def do_size_delta(target: InxUIScreenComponent, end_value: Vector2, duration: float, snapping: bool=False):
    def write(value):
        target.width, target.height = value

    end = end_value if isinstance(end_value, Vector2) else Vector2(*end_value)
    return _default_manager.to(lambda: Vector2(target.width, target.height), write, end,
                               duration).set_options(snapping).set_target(target)


def do_text(target: UIText, end_value: str, duration: float, rich_text_enabled: bool=True,
            scramble_mode: ScrambleMode=ScrambleMode.NONE, scramble_chars: str|None=None):
    if not isinstance(end_value, str):
        raise TypeError("end_value must be str")
    tween = StringTweener(lambda: target.text, lambda value: setattr(target, "text", value), end_value, duration)
    tween._font_size = target.font_size
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


def do_counter(target: UIText, from_value: int, end_value: int, duration: float,
               add_thousands_separator: bool=True, culture: CultureInfo|None=None):
    if type(from_value) is not int or type(end_value) is not int:
        raise TypeError("Counter values must be int")
    if culture is not None and not isinstance(culture, CultureInfo):
        raise TypeError("culture must be CultureInfo or None")
    formatter = (CultureInfo() if culture is None else culture).format_integer if add_thousands_separator else str
    def write(value):
        target.text = formatter(value)
    return _default_manager.to(lambda: from_value, write, end_value, duration).set_target(target)


def do_max_visible_characters(target: UIText, end_value: int, duration: float):
    if type(end_value) is not int:
        raise TypeError("end_value must be int")
    if target.max_visible_characters < 0:
        target.max_visible_characters = 0
    return _property(target, "max_visible_characters", end_value, duration)


def do_move_x(target: Transform|Rigidbody, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "position", 0, end_value, duration, snapping)


def do_move_y(target: Transform|Rigidbody, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "position", 1, end_value, duration, snapping)


def do_move_z(target: Transform|Rigidbody, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "position", 2, end_value, duration, snapping)


def do_local_move_x(target: Transform, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "local_position", 0, end_value, duration, snapping)


def do_local_move_y(target: Transform, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "local_position", 1, end_value, duration, snapping)


def do_local_move_z(target: Transform, end_value: float, duration: float, snapping: bool=False):
    return _axis(target, "local_position", 2, end_value, duration, snapping)


def do_scale_x(target: Transform, end_value: float, duration: float):
    return _axis(target, "local_scale", 0, end_value, duration)


def do_scale_y(target: Transform, end_value: float, duration: float):
    return _axis(target, "local_scale", 1, end_value, duration)


def do_scale_z(target: Transform, end_value: float, duration: float):
    return _axis(target, "local_scale", 2, end_value, duration)


def do_pitch(target: AudioSource, end_value: float, duration: float):
    return _property(target, "pitch", end_value, duration)


def do_intensity(target: Light, end_value: float, duration: float):
    return _property(target, "intensity", end_value, duration)


def do_shadow_strength(target: Light, end_value: float, duration: float):
    return _property(target, "shadow_strength", end_value, duration)


def do_field_of_view(target: Camera, end_value: float, duration: float):
    return _property(target, "field_of_view", end_value, duration)


def do_ortho_size(target: Camera, end_value: float, duration: float):
    return _property(target, "orthographic_size", end_value, duration)


def do_near_clip_plane(target: Camera, end_value: float, duration: float):
    return _property(target, "near_clip", end_value, duration)


def do_far_clip_plane(target: Camera, end_value: float, duration: float):
    return _property(target, "far_clip", end_value, duration)


def do_font_size(target: UIText, end_value: float, duration: float):
    return _property(target, "font_size", end_value, duration)


def do_time_scale(target: Tween, end_value: float, duration: float):
    return _property(target, "time_scale", end_value, duration)


def do_float(target: Material, end_value: float, property: str, duration: float):
    if not isinstance(property, str):
        raise TypeError("Material property must be str")
    if not target.has_property(property):
        return None
    return _default_manager.to(lambda: target.get_float(property), lambda value: target.set_float(property, value),
                      end_value, duration).set_target(target)


def do_vector(target: Material, end_value: vec4f, property: str, duration: float):
    if not isinstance(property, str):
        raise TypeError("Material property must be str")
    if not target.has_property(property):
        return None
    end = end_value if isinstance(end_value, vec4f) else vec4f(*end_value)
    return _default_manager.to(lambda: vec4f(*target.get_vector4(property)), lambda value: target.set_vector4(property, *value),
                               end, duration).set_target(target)


def do_complete(target: object, with_callbacks: bool=False): return _default_manager.complete(target, with_callbacks)


def do_kill(target: object, complete: bool=False): return _default_manager.kill(target, complete)


def do_flip(target: object): return _default_manager.flip(target)


def do_goto(target: object, to: float, and_play: bool=False): return _default_manager.goto(target, to, and_play)


def do_pause(target: object): return _default_manager.pause(target)


def do_play(target: object): return _default_manager.play(target)


def do_play_backwards(target: object): return _default_manager.play_backwards(target)


def do_play_forward(target: object): return _default_manager.play_forward(target)


def do_restart(target: object, include_delay: bool=True): return _default_manager.restart(target, include_delay)


def do_rewind(target: object, include_delay: bool=True): return _default_manager.rewind(target, include_delay)


def do_smooth_rewind(target: object): return _default_manager.smooth_rewind(target)


def do_toggle_pause(target: object): return _default_manager.toggle_pause(target)
