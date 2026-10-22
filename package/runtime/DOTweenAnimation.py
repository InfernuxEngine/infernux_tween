from enum import Enum

from infernux.components import FieldType, add_component_menu, serialized_field
from infernux.components.builtin import AudioSource, Camera, Light, Rigidbody, SpriteRenderer
from infernux.lib import Vector3
from infernux.ui import UIButton, UIGroup, UIImage, UIProgressBar, UISlider, UIText

from infernux_tween import ShortcutExtensions as S
from infernux_tween.authoring import TweenAuthoring


class AnimationType(str, Enum):
    Move = "Move"
    LocalMove = "LocalMove"
    Rotate = "Rotate"
    LocalRotate = "LocalRotate"
    Scale = "Scale"
    Color = "Color"
    Fade = "Fade"
    Value = "Value"
    Size = "Size"
    Float = "Float"
    PunchPosition = "PunchPosition"
    PunchRotation = "PunchRotation"
    PunchScale = "PunchScale"
    ShakePosition = "ShakePosition"
    ShakeRotation = "ShakeRotation"
    ShakeScale = "ShakeScale"
    FieldOfView = "FieldOfView"
    OrthoSize = "OrthoSize"
    Intensity = "Intensity"
    ShadowStrength = "ShadowStrength"
    Pitch = "Pitch"


class TargetKind(str, Enum):
    Transform = "Transform"
    Rigidbody = "Rigidbody"
    Text = "Text"
    Image = "Image"
    Button = "Button"
    CanvasGroup = "CanvasGroup"
    Slider = "Slider"
    ProgressBar = "ProgressBar"
    Sprite = "Sprite"
    Light = "Light"
    Camera = "Camera"
    Audio = "Audio"
    Material = "Material"


_TARGETS = {TargetKind.Rigidbody: Rigidbody, TargetKind.Text: UIText, TargetKind.Image: UIImage,
            TargetKind.Button: UIButton, TargetKind.CanvasGroup: UIGroup, TargetKind.Slider: UISlider,
            TargetKind.ProgressBar: UIProgressBar, TargetKind.Sprite: SpriteRenderer, TargetKind.Light: Light,
            TargetKind.Camera: Camera, TargetKind.Audio: AudioSource}
_VECTOR = {AnimationType[name] for name in ("Move", "LocalMove", "Rotate", "LocalRotate", "Scale",
           "PunchPosition", "PunchRotation", "PunchScale", "ShakePosition", "ShakeRotation", "ShakeScale")}
_PROPERTIES = {AnimationType.Move: "position", AnimationType.LocalMove: "local_position",
               AnimationType.Rotate: "euler_angles", AnimationType.LocalRotate: "local_euler_angles",
               AnimationType.Scale: "local_scale", AnimationType.FieldOfView: "field_of_view",
               AnimationType.OrthoSize: "orthographic_size", AnimationType.Intensity: "intensity",
               AnimationType.ShadowStrength: "shadow_strength", AnimationType.Pitch: "pitch"}
_COMPATIBLE = {
    AnimationType.Move: {TargetKind.Transform, TargetKind.Rigidbody},
    AnimationType.Rotate: {TargetKind.Transform, TargetKind.Rigidbody},
    AnimationType.Color: {TargetKind.Text, TargetKind.Image, TargetKind.Button, TargetKind.Sprite, TargetKind.Light, TargetKind.Camera, TargetKind.Material},
    AnimationType.Fade: {TargetKind.Text, TargetKind.Image, TargetKind.Button, TargetKind.Sprite, TargetKind.CanvasGroup, TargetKind.Audio, TargetKind.Material},
    AnimationType.Value: {TargetKind.Slider, TargetKind.ProgressBar},
    AnimationType.Size: {TargetKind.Text, TargetKind.Image, TargetKind.Button},
    AnimationType.Float: {TargetKind.Material},
    AnimationType.FieldOfView: {TargetKind.Camera}, AnimationType.OrthoSize: {TargetKind.Camera},
    AnimationType.Intensity: {TargetKind.Light}, AnimationType.ShadowStrength: {TargetKind.Light},
    AnimationType.Pitch: {TargetKind.Audio},
}


@add_component_menu("Animation/Tween Animation")
class DOTweenAnimation(TweenAuthoring):
    animation_type: AnimationType = serialized_field(default=AnimationType.LocalMove, display_name_key="tween.animation_type",
                                                     enum_labels=["tween.animation."+e.name for e in AnimationType])
    target_kind: TargetKind = serialized_field(default=TargetKind.Transform, display_name_key="tween.target_kind",
                                              enum_labels=["tween.target_kind."+e.name for e in TargetKind])
    material = serialized_field(default=None, field_type=FieldType.MATERIAL, display_name_key="tween.material",
                                visible_when=lambda c: c.target_kind == TargetKind.Material)
    end_vector = serialized_field(default=(0.0, 1.0, 0.0), field_type=FieldType.VEC3, display_name_key="tween.end_vector",
                                  visible_when=lambda c: c.animation_type in _VECTOR)
    end_color = serialized_field(default=[1.0, 1.0, 1.0, 1.0], field_type=FieldType.COLOR, display_name_key="tween.end_color",
                                 visible_when=lambda c: c.animation_type == AnimationType.Color)
    end_size = serialized_field(default=(100.0, 40.0), field_type=FieldType.VEC2, display_name_key="tween.end_size",
                                visible_when=lambda c: c.animation_type == AnimationType.Size)
    end_value: float = serialized_field(default=1.0, display_name_key="tween.end_value",
                                        visible_when=lambda c: c.animation_type not in _VECTOR | {AnimationType.Color, AnimationType.Size})
    property_name: str = serialized_field(default="baseColor", display_name_key="tween.material_property",
                                          visible_when=lambda c: c.target_kind == TargetKind.Material)
    vibrato: int = serialized_field(default=10, range=(1, 100), slider=False, display_name_key="tween.vibrato",
                                    visible_when=lambda c: c.animation_type.name.startswith(("Punch", "Shake")))
    seed: int = serialized_field(default=0, display_name_key="tween.seed",
                                 visible_when=lambda c: c.animation_type.name.startswith("Shake"))
    is_from: bool = serialized_field(default=False, display_name_key="tween.from",
                                     visible_when=lambda c: not c.animation_type.name.startswith(("Punch", "Shake")))

    def _resolve_target(self, preview=False):
        if self.target_kind == TargetKind.Material:
            if self.material is None:
                raise ValueError("Select the material to animate")
            return self.material
        obj = self._target_object()
        if self.target_kind == TargetKind.Transform or (preview and self.target_kind == TargetKind.Rigidbody):
            return obj.transform
        target = obj.get_component(_TARGETS[self.target_kind])
        if target is None:
            raise ValueError(f"{obj.name} needs {_TARGETS[self.target_kind].__name__}")
        return target

    def _build(self, preview=False):
        if self.target_kind not in _COMPATIBLE.get(self.animation_type, {TargetKind.Transform}):
            raise ValueError(f"{self.animation_type.value} does not animate {self.target_kind.value}")
        target, kind = self._resolve_target(preview), self.animation_type
        shortcut = getattr(S, "DO" + kind.name)
        if kind.name.startswith("Shake"):
            return shortcut(target, self.duration, Vector3(*self.end_vector), self.vibrato, seed=self.seed)
        if kind.name.startswith("Punch"):
            return shortcut(target, Vector3(*self.end_vector), self.duration, self.vibrato)
        if kind == AnimationType.Float:
            return shortcut(target, self.end_value, self.property_name, self.duration)
        end = self.end_vector if kind in _VECTOR else (self.end_color if kind == AnimationType.Color else
              self.end_size if kind == AnimationType.Size else self.end_value)
        if self.target_kind == TargetKind.Material:
            return shortcut(target, end, self.duration, property=self.property_name)
        return shortcut(target, end, self.duration)

    def _after_configure(self, tween):
        if self.is_from:
            if self.animation_type.name.startswith(("Punch", "Shake")):
                raise ValueError("Punch and Shake already return to their original pose")
            tween.From(self.relative)

    def _capture_preview(self, scope):
        target, kind = self._resolve_target(True), self.animation_type
        if self.target_kind == TargetKind.Material:
            scope.capture_material(target)
        elif kind in _PROPERTIES:
            scope.capture(target, _PROPERTIES[kind])
        elif kind.name.startswith(("Punch", "Shake")):
            name = {"Position": "local_position", "Rotation": "local_euler_angles", "Scale": "local_scale"}
            scope.capture(target, name[kind.name[5:]])
        elif kind == AnimationType.Color:
            scope.capture(target, {TargetKind.Sprite: "sprite_color", TargetKind.Button: "background_color"}.get(self.target_kind, "color"))
        elif kind == AnimationType.Fade:
            scope.capture(target, {TargetKind.Sprite: "sprite_color", TargetKind.Audio: "volume", TargetKind.CanvasGroup: "alpha"}.get(self.target_kind, "opacity"))
        elif kind == AnimationType.Size:
            scope.capture(target, "width", "height")
        elif kind == AnimationType.Value:
            scope.capture(target, "value")
