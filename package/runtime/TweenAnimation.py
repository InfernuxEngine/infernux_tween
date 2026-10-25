from enum import Enum

from infernux.components import FieldType, InxComponent, add_component_menu, serialized_field
from infernux.components.builtin import AudioSource, Camera, Light, Rigidbody, SpriteRenderer
from infernux.lib import Transform, Vector3
from infernux.ui import UIButton, UIGroup, UIImage, UIProgressBar, UISlider, UIText

from infernux_tween import RotateMode, ScrambleMode, ShakeRandomnessMode, shortcuts as S
from .TweenAuthoring import TweenAuthoring


class AnimationType(Enum):
    MOVE = "Move"
    LOCAL_MOVE = "LocalMove"
    ROTATE = "Rotate"
    LOCAL_ROTATE = "LocalRotate"
    SCALE = "Scale"
    COLOR = "Color"
    FADE = "Fade"
    VALUE = "Value"
    SIZE = "Size"
    FLOAT = "Float"
    PUNCH_POSITION = "PunchPosition"
    PUNCH_ROTATION = "PunchRotation"
    PUNCH_SCALE = "PunchScale"
    SHAKE_POSITION = "ShakePosition"
    SHAKE_ROTATION = "ShakeRotation"
    SHAKE_SCALE = "ShakeScale"
    FIELD_OF_VIEW = "FieldOfView"
    ORTHO_SIZE = "OrthoSize"
    INTENSITY = "Intensity"
    SHADOW_STRENGTH = "ShadowStrength"
    PITCH = "Pitch"
    TEXT = "Text"


class TargetKind(Enum):
    AUTO = "Auto"
    TRANSFORM = "Transform"
    RIGIDBODY = "Rigidbody"
    TEXT = "Text"
    IMAGE = "Image"
    BUTTON = "Button"
    CANVAS_GROUP = "CanvasGroup"
    SLIDER = "Slider"
    PROGRESS_BAR = "ProgressBar"
    SPRITE = "Sprite"
    LIGHT = "Light"
    CAMERA = "Camera"
    AUDIO = "Audio"
    MATERIAL = "Material"


_TARGETS = {TargetKind.RIGIDBODY: Rigidbody, TargetKind.TEXT: UIText, TargetKind.IMAGE: UIImage,
            TargetKind.BUTTON: UIButton, TargetKind.CANVAS_GROUP: UIGroup, TargetKind.SLIDER: UISlider,
            TargetKind.PROGRESS_BAR: UIProgressBar, TargetKind.SPRITE: SpriteRenderer, TargetKind.LIGHT: Light,
            TargetKind.CAMERA: Camera, TargetKind.AUDIO: AudioSource}
_VECTOR = {AnimationType[name] for name in ("MOVE", "LOCAL_MOVE", "ROTATE", "LOCAL_ROTATE", "SCALE",
           "PUNCH_POSITION", "PUNCH_ROTATION", "PUNCH_SCALE", "SHAKE_POSITION", "SHAKE_ROTATION", "SHAKE_SCALE")}
_SHORTCUTS = {kind: getattr(S, "do_size_delta" if kind == AnimationType.SIZE else "do_" + kind.name.lower())
              for kind in AnimationType}
_PROPERTIES = {AnimationType.MOVE: "position", AnimationType.LOCAL_MOVE: "local_position",
               AnimationType.ROTATE: "euler_angles", AnimationType.LOCAL_ROTATE: "local_euler_angles",
               AnimationType.SCALE: "local_scale", AnimationType.FIELD_OF_VIEW: "field_of_view",
               AnimationType.ORTHO_SIZE: "orthographic_size", AnimationType.INTENSITY: "intensity",
               AnimationType.SHADOW_STRENGTH: "shadow_strength", AnimationType.PITCH: "pitch"}
_COMPATIBLE = {
    AnimationType.MOVE: {TargetKind.TRANSFORM, TargetKind.RIGIDBODY},
    AnimationType.ROTATE: {TargetKind.TRANSFORM, TargetKind.RIGIDBODY},
    AnimationType.COLOR: {TargetKind.TEXT, TargetKind.IMAGE, TargetKind.BUTTON, TargetKind.SPRITE, TargetKind.LIGHT, TargetKind.CAMERA, TargetKind.MATERIAL},
    AnimationType.FADE: {TargetKind.TEXT, TargetKind.IMAGE, TargetKind.BUTTON, TargetKind.SPRITE, TargetKind.CANVAS_GROUP, TargetKind.AUDIO, TargetKind.MATERIAL},
    AnimationType.VALUE: {TargetKind.SLIDER, TargetKind.PROGRESS_BAR},
    AnimationType.SIZE: {TargetKind.TEXT, TargetKind.IMAGE, TargetKind.BUTTON},
    AnimationType.FLOAT: {TargetKind.MATERIAL},
    AnimationType.FIELD_OF_VIEW: {TargetKind.CAMERA}, AnimationType.ORTHO_SIZE: {TargetKind.CAMERA},
    AnimationType.INTENSITY: {TargetKind.LIGHT}, AnimationType.SHADOW_STRENGTH: {TargetKind.LIGHT},
    AnimationType.PITCH: {TargetKind.AUDIO},
    AnimationType.TEXT: {TargetKind.TEXT},
}


_SNAPPING = {AnimationType.MOVE, AnimationType.LOCAL_MOVE, AnimationType.PUNCH_POSITION,
             AnimationType.SHAKE_POSITION}
_UNIFORM = {AnimationType.SCALE, AnimationType.SIZE}


@add_component_menu("Animation/Tween Animation")
class TweenAnimation(TweenAuthoring):
    _animation_target_override = None
    _group_uses_owner = False
    animation_type: AnimationType = serialized_field(default=AnimationType.LOCAL_MOVE, display_name_key="tween.animation_type",
                                                     enum_labels=["tween.animation."+e.name for e in AnimationType])
    target_kind: TargetKind = serialized_field(default=TargetKind.AUTO, display_name_key="tween.target_kind",
                                              enum_labels=["tween.target_kind."+e.name for e in TargetKind])
    material = serialized_field(default=None, field_type=FieldType.MATERIAL, display_name_key="tween.material",
                                visible_when=lambda c: c.target_kind == TargetKind.MATERIAL)
    end_vector = serialized_field(default=(0.0, 1.0, 0.0), field_type=FieldType.VEC3, display_name_key="tween.end_vector",
        visible_when=lambda c: c.animation_type in _VECTOR and not (c.animation_type == AnimationType.SCALE and c.optional_bool0))
    end_color = serialized_field(default=[1.0, 1.0, 1.0, 1.0], field_type=FieldType.COLOR, display_name_key="tween.end_color",
                                 visible_when=lambda c: c.animation_type == AnimationType.COLOR)
    end_size = serialized_field(default=(100.0, 40.0), field_type=FieldType.VEC2, display_name_key="tween.end_size",
        visible_when=lambda c: c.animation_type == AnimationType.SIZE and not c.optional_bool0)
    end_value: float = serialized_field(default=1.0, display_name_key="tween.end_value",
        visible_when=lambda c: c.animation_type not in _VECTOR | {AnimationType.COLOR, AnimationType.SIZE, AnimationType.TEXT}
        or c.animation_type in _UNIFORM and c.optional_bool0)
    end_text: str = serialized_field(default="", multiline=True, display_name_key="tween.end_text",
                                     visible_when=lambda c: c.animation_type == AnimationType.TEXT)
    optional_bool0: bool = serialized_field(default=False, hidden=True)
    optional_bool1: bool = serialized_field(default=True, display_name_key="tween.fade_out",
        visible_when=lambda c: c.animation_type.name.startswith("SHAKE_"))
    optional_rotation_mode: RotateMode = serialized_field(default=RotateMode.FAST, display_name_key="tween.rotation_mode",
        enum_labels=["tween.rotation_mode."+e.name for e in RotateMode],
        visible_when=lambda c: c.animation_type in (AnimationType.ROTATE, AnimationType.LOCAL_ROTATE))
    optional_scramble_mode: ScrambleMode = serialized_field(default=ScrambleMode.NONE, display_name_key="tween.scramble_mode",
                                                    enum_labels=["tween.scramble."+e.name for e in ScrambleMode],
                                                    visible_when=lambda c: c.animation_type == AnimationType.TEXT)
    optional_string: str = serialized_field(default="", display_name_key="tween.scramble_chars",
        visible_when=lambda c: c.animation_type == AnimationType.TEXT and c.optional_scramble_mode == ScrambleMode.CUSTOM)
    property_name: str = serialized_field(default="baseColor", display_name_key="tween.material_property",
                                          visible_when=lambda c: c.target_kind == TargetKind.MATERIAL)
    optional_int0: int = serialized_field(default=10, range=(1, 100), slider=False, display_name_key="tween.vibrato",
                                    visible_when=lambda c: c.animation_type.name.startswith(("PUNCH_", "SHAKE_")))
    optional_float0: float = serialized_field(default=1.0, hidden=True)
    optional_shake_randomness_mode: ShakeRandomnessMode = serialized_field(default=ShakeRandomnessMode.FULL,
        display_name_key="tween.randomness_mode", enum_labels=["tween.randomness_mode."+e.name for e in ShakeRandomnessMode],
        visible_when=lambda c: c.animation_type.name.startswith("SHAKE_"))
    is_from: bool = serialized_field(default=False, display_name_key="tween.from",
                                     visible_when=lambda c: not c.animation_type.name.startswith(("PUNCH_", "SHAKE_")))

    def _resolve_kind(self):
        if self.target_kind != TargetKind.AUTO:
            return self.target_kind
        compatible = _COMPATIBLE.get(self.animation_type, {TargetKind.TRANSFORM})
        obj = self._target_object()
        if TargetKind.TRANSFORM in compatible:
            return TargetKind.RIGIDBODY if TargetKind.RIGIDBODY in compatible and obj.get_component(Rigidbody) is not None else TargetKind.TRANSFORM
        candidates = [kind for kind in sorted(compatible, key=lambda kind: kind.value)
                      if kind != TargetKind.MATERIAL and obj.get_component(_TARGETS[kind]) is not None]
        if len(candidates) != 1:
            raise ValueError(f"Select Target Component for {self.animation_type.value}: {len(candidates)} suitable components on {obj.name}")
        return candidates[0]

    def _resolve_target(self, preview=False, kind=None):
        if self._animation_target_override is not None:
            target = self._animation_target_override
            return target.transform if preview and isinstance(target, Rigidbody) else target
        kind = self._resolve_kind() if kind is None else kind
        if kind == TargetKind.MATERIAL:
            if self.material is None:
                raise ValueError("Select the material to animate")
            return self.material
        obj = self._target_object()
        if kind == TargetKind.TRANSFORM or (preview and kind == TargetKind.RIGIDBODY):
            return obj.transform
        target = obj.get_component(_TARGETS[kind])
        if target is None:
            raise ValueError(f"{obj.name} needs {_TARGETS[kind].__name__}")
        return target

    def set_animation_target(self, tween_target: InxComponent | Transform,
                             use_tween_target_game_object_for_group_operations: bool=True) -> None:
        kind = self._resolve_kind()
        if not isinstance(tween_target, type(self._resolve_target(kind=kind))):
            raise TypeError("The animation target must have the same component type")
        self.target, self.target_kind = tween_target.game_object, kind
        self._animation_target_override = tween_target
        self._group_uses_owner = not use_tween_target_game_object_for_group_operations

    def _group_target(self):
        return self.game_object if self._group_uses_owner else self._target_object()

    def _restart_from_here(self):
        kind = self.animation_type
        if kind in (AnimationType.MOVE, AnimationType.LOCAL_MOVE):
            start = getattr(self._resolve_target(), _PROPERTIES[kind])
            self._tween.change_values(start, start + Vector3(*self.end_vector))

    def _lifetime_target(self):
        return self.game_object if self.target_kind == TargetKind.MATERIAL else self._target_object()

    def _build(self, preview=False):
        target_kind = self._resolve_kind()
        if target_kind not in _COMPATIBLE.get(self.animation_type, {TargetKind.TRANSFORM}):
            raise ValueError(f"{self.animation_type.value} does not animate {target_kind.value}")
        target, kind = self._resolve_target(preview, target_kind), self.animation_type
        shortcut = _SHORTCUTS[kind]
        if kind == AnimationType.TEXT:
            return shortcut(target, self.end_text, self.duration, self.optional_bool0, self.optional_scramble_mode,
                            self.optional_string or None)
        if kind.name.startswith("SHAKE_"):
            options = dict(vibrato=self.optional_int0, randomness=self.optional_float0,
                           fade_out=self.optional_bool1, randomness_mode=self.optional_shake_randomness_mode)
            if kind == AnimationType.SHAKE_POSITION:
                options['snapping'] = self.optional_bool0
            return shortcut(target, self.duration, Vector3(*self.end_vector), **options)
        if kind.name.startswith("PUNCH_"):
            options = dict(vibrato=self.optional_int0, elasticity=self.optional_float0)
            if kind == AnimationType.PUNCH_POSITION:
                options['snapping'] = self.optional_bool0
            return shortcut(target, Vector3(*self.end_vector), self.duration, **options)
        if kind == AnimationType.FLOAT:
            return shortcut(target, self.end_value, self.property_name, self.duration)
        end = self.end_vector if kind in _VECTOR else (self.end_color if kind == AnimationType.COLOR else
              self.end_size if kind == AnimationType.SIZE else self.end_value)
        if kind in _UNIFORM and self.optional_bool0:
            end = (self.end_value,) * (3 if kind == AnimationType.SCALE else 2)
        if target_kind == TargetKind.MATERIAL:
            return shortcut(target, end, self.property_name, self.duration)
        if kind in (AnimationType.ROTATE, AnimationType.LOCAL_ROTATE):
            return shortcut(target, end, self.duration, self.optional_rotation_mode)
        if kind in (AnimationType.MOVE, AnimationType.LOCAL_MOVE):
            return shortcut(target, end, self.duration, self.optional_bool0)
        return shortcut(target, end, self.duration)

    def _after_configure(self, tween):
        if self.is_from:
            if self.animation_type.name.startswith(("PUNCH_", "SHAKE_")):
                raise ValueError("Punch and Shake already return to their original pose")
            tween.from_(self.relative)

    def _capture_preview(self, scope):
        target_kind = self._resolve_kind()
        target, kind = self._resolve_target(True, target_kind), self.animation_type
        if target_kind == TargetKind.MATERIAL:
            scope.capture_material(target)
        elif kind in _PROPERTIES:
            scope.capture(target, _PROPERTIES[kind])
        elif kind.name.startswith(("PUNCH_", "SHAKE_")):
            name = {"POSITION": "local_position", "ROTATION": "local_euler_angles", "SCALE": "local_scale"}
            scope.capture(target, name[kind.name.split("_", 1)[1]])
        elif kind == AnimationType.COLOR:
            scope.capture(target, {TargetKind.SPRITE: "sprite_color", TargetKind.BUTTON: "background_color",
                                   TargetKind.CAMERA: "background_color"}.get(target_kind, "color"))
        elif kind == AnimationType.FADE:
            scope.capture(target, {TargetKind.SPRITE: "sprite_color", TargetKind.AUDIO: "volume", TargetKind.CANVAS_GROUP: "alpha",
                                   TargetKind.BUTTON: "background_color"}.get(target_kind, "color"))
        elif kind == AnimationType.SIZE:
            scope.capture(target, "width", "height")
        elif kind == AnimationType.VALUE:
            scope.capture(target, "value")
        elif kind == AnimationType.TEXT:
            scope.capture_text(target)
            scope.capture(target, "text", "rich_text")
