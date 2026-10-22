"""DOTween-style shortcuts using Infernux's native target properties."""

from functools import singledispatch

from infernux.components.builtin import AudioSource, Camera, Light, Rigidbody, SpriteRenderer
from infernux.core.material import Material
from infernux.lib import Transform, Vector3, quatf
from infernux.ui import InxUIScreenComponent, UIButton, UIGroup, UIImage, UIText

from .core import DOTween, LoopType, Tweener, UpdateType
from .path import DOPath, DOLocalPath
from .rotation import DORotateQuaternion, DOLocalRotateQuaternion, RotateMode
from .motion import (DOBlendableLocalMoveBy, DOBlendableMoveBy, DOBlendableScaleBy,
                     DOBlendableRotateBy, DOBlendableLocalRotateBy, DOSpiral,
                     DOJump, DOLocalJump, DOPunchPosition, DOPunchRotation, DOPunchScale,
                     DOShakePosition, DOShakeRotation, DOShakeScale)


def _vector(value):
    return value if isinstance(value, Vector3) else Vector3(*value)


def _property(target, name, to, duration):
    return DOTween.To(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                      to, duration).SetTarget(target)


def _move(target, name, to, duration, snapping=False):
    end = _vector(to)
    setter = lambda value: setattr(target, name, value)
    if isinstance(target, Rigidbody):
        if name != "position":
            raise TypeError("Rigidbody motion uses world-space position")
        setter = target.move_position
    elif not isinstance(target, Transform):
        raise TypeError("Motion shortcuts require a Transform or Rigidbody")
    if snapping:
        write = setter
        setter = lambda value: write(Vector3(round(value.x), round(value.y), round(value.z)))
    tween = DOTween.To(lambda: getattr(target, name), setter, end, duration).SetTarget(target)
    if isinstance(target, Rigidbody):
        tween.SetUpdate(UpdateType.Fixed)
    return tween


def _axis(target, name, axis, to, duration, snapping=False):
    getter = lambda: getattr(target, name)[axis]

    def write(value):
        current = getattr(target, name)
        current[axis] = value
        setattr(target, name, current)

    if isinstance(target, Rigidbody):
        if name != "position":
            raise TypeError("Rigidbody motion uses world-space position")
        locked = [None]

        def getter():
            locked[0] = target.position
            return locked[0][axis]

        def write(value):
            locked[0][axis] = value
            target.move_position(locked[0])

    setter = (lambda value: write(round(value))) if snapping else write
    tween = DOTween.To(getter, setter, to, duration).SetTarget(target)
    if isinstance(target, Rigidbody):
        tween.SetUpdate(UpdateType.Fixed)
    return tween


class _EulerTweener(Tweener):
    def __init__(self, target, name, to, duration, mode):
        if isinstance(target, Rigidbody):
            if name != "euler_angles":
                raise TypeError("Rigidbody rotation uses world coordinates")
            super().__init__(lambda: target.rotation.euler_angles,
                             lambda value: target.move_rotation(quatf.euler(*value)), _vector(to), duration)
            self.update_type = UpdateType.Fixed
        else:
            super().__init__(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                             _vector(to), duration)
        self.mode = RotateMode(mode)

    def _initialize(self):
        if self._start is not None:
            return
        speed = self.duration if self._speed_based else None
        super()._initialize()
        if self.mode == RotateMode.Fast:
            self._delta = Vector3(*((self._delta[i] + 180) % 360 - 180 for i in range(3)))
            if speed is not None:
                self.duration = self._delta.magnitude / speed


def DOMove(target, to, duration, snapping=False):
    return _move(target, "position", to, duration, snapping)


def DOLocalMove(target, to, duration, snapping=False):
    return _move(target, "local_position", to, duration, snapping)


def DOScale(target, to, duration):
    end = Vector3(to, to, to) if isinstance(to, (int, float)) else _vector(to)
    return _property(target, "local_scale", end, duration)


def DORotate(target, to, duration, mode=RotateMode.Fast):
    return DOTween.add(_EulerTweener(target, "euler_angles", to, duration, mode)).SetTarget(target)


def DOLocalRotate(target, to, duration, mode=RotateMode.Fast):
    return DOTween.add(_EulerTweener(target, "local_euler_angles", to, duration, mode)).SetTarget(target)


@singledispatch
def DOColor(target, to, duration):
    raise TypeError(f"DOColor does not support {type(target).__name__}")


@DOColor.register(UIText)
@DOColor.register(UIImage)
def _ui_color(target, to, duration):
    return _property(target, "color", list(to), duration)


@DOColor.register(UIButton)
def _button_color(target, to, duration):
    return _property(target, "background_color", list(to), duration)


@DOColor.register(SpriteRenderer)
def _sprite_color(target, to, duration):
    return _property(target, "sprite_color", list(to), duration)


@DOColor.register(Camera)
def _camera_color(target, to, duration):
    return _property(target, "background_color", list(to), duration)


@DOColor.register(Light)
def _light_color(target, to, duration):
    return _property(target, "color", [to[i] for i in range(3)]+[target.color[3]], duration)


@DOColor.register(Material)
def _material_color(target, to, duration, property="baseColor"):
    return DOTween.To(lambda: target.get_color(property), lambda value: target.set_color(property, *value),
                      tuple(to), duration).SetTarget(target)


class _BlendableColorTween(Tweener):
    def __init__(self, getter, setter, to, duration):
        start = list(getter())
        self._read_current = getter
        super().__init__(lambda: start, setter, to, duration)

    def _initialize(self):
        if self._start is None:
            super()._initialize()
            self._applied = (0.0,)*len(self._delta)

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        factor = self._ease(progress)+(cycle if self.loop_type == LoopType.Incremental else 0)
        offset = tuple(delta*factor for delta in self._delta)
        if self._snapping:
            offset = tuple(round(start+item)-start for start, item in zip(self._start, offset))
        if self._constraint or self._alpha_only:
            offset = tuple(value if (i == 3 if self._alpha_only else self._constraint & (1 << i)) else 0.0
                           for i, value in enumerate(offset))
        current = self._read_current()
        value = self._value_type(value+offset[i]-self._applied[i] for i, value in enumerate(current))
        self._setter(value)
        self._applied = offset


def _blendable_color_property(target, name, to, duration):
    return DOTween.add(_BlendableColorTween(lambda: getattr(target, name), lambda value: setattr(target, name, value),
                                           list(to), duration)).SetTarget(target)


@singledispatch
def DOBlendableColor(target, to, duration):
    raise TypeError(f"DOBlendableColor does not support {type(target).__name__}")


@DOBlendableColor.register(UIText)
@DOBlendableColor.register(UIImage)
@DOBlendableColor.register(Camera)
def _blendable_ui_color(target, to, duration):
    return _blendable_color_property(target, "background_color" if isinstance(target, Camera) else "color", to, duration)


@DOBlendableColor.register(UIButton)
def _blendable_button_color(target, to, duration):
    return _blendable_color_property(target, "background_color", to, duration)


@DOBlendableColor.register(SpriteRenderer)
def _blendable_sprite_color(target, to, duration):
    return _blendable_color_property(target, "sprite_color", to, duration)


@DOBlendableColor.register(Light)
def _blendable_light_color(target, to, duration):
    return _blendable_color_property(target, "color", [to[i] for i in range(3)]+[target.color[3]], duration)


@DOBlendableColor.register(Material)
def _blendable_material_color(target, to, duration, property="baseColor"):
    return DOTween.add(_BlendableColorTween(lambda: target.get_color(property), lambda value: target.set_color(property, *value),
                                           tuple(to), duration)).SetTarget(target)


@singledispatch
def DOFade(target, to, duration):
    raise TypeError(f"DOFade does not support {type(target).__name__}")


@DOFade.register(InxUIScreenComponent)
def _ui_fade(target, to, duration):
    return _property(target, "opacity", to, duration)


@DOFade.register(UIGroup)
def _group_fade(target, to, duration):
    return _property(target, "alpha", to, duration)


@DOFade.register(AudioSource)
def _audio_fade(target, to, duration):
    return _property(target, "volume", to, duration)


@DOFade.register(SpriteRenderer)
def _sprite_fade(target, to, duration):
    def write(alpha):
        color = list(target.sprite_color)
        color[3] = alpha
        target.sprite_color = color

    return DOTween.To(lambda: target.sprite_color[3], write, to, duration).SetTarget(target)


@DOFade.register(Material)
def _material_fade(target, to, duration, property="baseColor"):
    def write(alpha):
        color = list(target.get_color(property))
        color[3] = alpha
        target.set_color(property, *color)

    return DOTween.To(lambda: target.get_color(property)[3], write, to, duration).SetTarget(target)


def DOValue(target, to, duration, snapping=False, *, notify=True):
    write = lambda value: target.set_value(value, notify=notify)
    setter = (lambda value: write(round(value))) if snapping else write
    return DOTween.To(lambda: target.value, setter, to, duration).SetTarget(target)


def DOSize(target, to, duration):
    def write(value):
        target.width, target.height = value

    return DOTween.To(lambda: (target.width, target.height), write, tuple(to), duration).SetTarget(target)


class ShortcutExtensions:
    """Python equivalent of extension calls: DOMove(transform, end, seconds)."""

    DOMove = staticmethod(DOMove)
    DOLocalMove = staticmethod(DOLocalMove)
    DOScale = staticmethod(DOScale)
    DORotate = staticmethod(DORotate)
    DOLocalRotate = staticmethod(DOLocalRotate)
    DOColor = staticmethod(DOColor)
    DOFade = staticmethod(DOFade)
    DOValue = staticmethod(DOValue)
    DOSize = staticmethod(DOSize)
    DOPath = staticmethod(DOPath)
    DOLocalPath = staticmethod(DOLocalPath)
    DORotateQuaternion = staticmethod(DORotateQuaternion)
    DOLocalRotateQuaternion = staticmethod(DOLocalRotateQuaternion)
    DOJump = staticmethod(DOJump)
    DOLocalJump = staticmethod(DOLocalJump)
    DOPunchPosition = staticmethod(DOPunchPosition)
    DOPunchRotation = staticmethod(DOPunchRotation)
    DOPunchScale = staticmethod(DOPunchScale)
    DOShakePosition = staticmethod(DOShakePosition)
    DOShakeRotation = staticmethod(DOShakeRotation)
    DOShakeScale = staticmethod(DOShakeScale)
    DOBlendableMoveBy = staticmethod(DOBlendableMoveBy)
    DOBlendableLocalMoveBy = staticmethod(DOBlendableLocalMoveBy)
    DOBlendableScaleBy = staticmethod(DOBlendableScaleBy)
    DOBlendableRotateBy = staticmethod(DOBlendableRotateBy)
    DOBlendableLocalRotateBy = staticmethod(DOBlendableLocalRotateBy)
    DOBlendableColor = staticmethod(DOBlendableColor)
    DOSpiral = staticmethod(DOSpiral)

    @staticmethod
    def DOMoveX(target, to, duration, snapping=False): return _axis(target, "position", 0, to, duration, snapping)
    @staticmethod
    def DOMoveY(target, to, duration, snapping=False): return _axis(target, "position", 1, to, duration, snapping)
    @staticmethod
    def DOMoveZ(target, to, duration, snapping=False): return _axis(target, "position", 2, to, duration, snapping)
    @staticmethod
    def DOLocalMoveX(target, to, duration, snapping=False): return _axis(target, "local_position", 0, to, duration, snapping)
    @staticmethod
    def DOLocalMoveY(target, to, duration, snapping=False): return _axis(target, "local_position", 1, to, duration, snapping)
    @staticmethod
    def DOLocalMoveZ(target, to, duration, snapping=False): return _axis(target, "local_position", 2, to, duration, snapping)
    @staticmethod
    def DOScaleX(target, to, duration): return _axis(target, "local_scale", 0, to, duration)
    @staticmethod
    def DOScaleY(target, to, duration): return _axis(target, "local_scale", 1, to, duration)
    @staticmethod
    def DOScaleZ(target, to, duration): return _axis(target, "local_scale", 2, to, duration)
    @staticmethod
    def DOPitch(target, to, duration): return _property(target, "pitch", to, duration)
    @staticmethod
    def DOIntensity(target, to, duration): return _property(target, "intensity", to, duration)
    @staticmethod
    def DOShadowStrength(target, to, duration): return _property(target, "shadow_strength", to, duration)
    @staticmethod
    def DOFieldOfView(target, to, duration): return _property(target, "field_of_view", to, duration)
    @staticmethod
    def DOOrthoSize(target, to, duration): return _property(target, "orthographic_size", to, duration)
    @staticmethod
    def DOFloat(target, to, property, duration):
        return DOTween.To(lambda: target.get_float(property), lambda value: target.set_float(property, value),
                          to, duration).SetTarget(target)
