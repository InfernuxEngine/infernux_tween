from enum import Enum

from infernux.components import FieldType, add_component_menu, serialized_field
from infernux.components.builtin import AudioSource, Camera, Light, Rigidbody, SpriteRenderer
from infernux.lib import Vector3
from infernux.ui import UIButton, UIGroup, UIImage, UIProgressBar, UISlider, UIText

from infernux_tween import ScrambleMode, ShortcutExtensions as S
from .TweenAuthoring import TweenAuthoring


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
    Text = "Text"


class TargetKind(str, Enum):
    Auto = "Auto"
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
    AnimationType.Text: {TargetKind.Text},
}


@add_component_menu("Animation/Tween Animation")
class DOTweenAnimation(TweenAuthoring):
    animation_type: AnimationType = serialized_field(default=AnimationType.LocalMove, display_name_key="tween.animation_type",
                                                     enum_labels=["tween.animation."+e.name for e in AnimationType])
    target_kind: TargetKind = serialized_field(default=TargetKind.Auto, display_name_key="tween.target_kind",
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
                                        visible_when=lambda c: c.animation_type not in _VECTOR | {AnimationType.Color, AnimationType.Size, AnimationType.Text})
    end_text: str = serialized_field(default="", multiline=True, display_name_key="tween.end_text",
                                     visible_when=lambda c: c.animation_type == AnimationType.Text)
    rich_text: bool = serialized_field(default=True, display_name_key="tween.rich_text",
                                       visible_when=lambda c: c.animation_type == AnimationType.Text)
    scramble_mode: ScrambleMode = serialized_field(default=ScrambleMode.None_, display_name_key="tween.scramble_mode",
                                                    enum_labels=["tween.scramble."+e.name for e in ScrambleMode],
                                                    visible_when=lambda c: c.animation_type == AnimationType.Text)
    scramble_chars: str = serialized_field(default="", display_name_key="tween.scramble_chars",
                                           visible_when=lambda c: c.animation_type == AnimationType.Text and c.scramble_mode == ScrambleMode.Custom)
    property_name: str = serialized_field(default="baseColor", display_name_key="tween.material_property",
                                          visible_when=lambda c: c.target_kind == TargetKind.Material)
    vibrato: int = serialized_field(default=10, range=(1, 100), slider=False, display_name_key="tween.vibrato",
                                    visible_when=lambda c: c.animation_type.name.startswith(("Punch", "Shake")))
    seed: int = serialized_field(default=0, display_name_key="tween.seed",
                                 visible_when=lambda c: c.animation_type.name.startswith("Shake") or
                                 (c.animation_type == AnimationType.Text and c.scramble_mode != ScrambleMode.None_))
    is_from: bool = serialized_field(default=False, display_name_key="tween.from",
                                     visible_when=lambda c: not c.animation_type.name.startswith(("Punch", "Shake")))

    def _resolve_kind(self):
        if self.target_kind != TargetKind.Auto:
            return self.target_kind
        compatible = _COMPATIBLE.get(self.animation_type, {TargetKind.Transform})
        obj = self._target_object()
        if TargetKind.Transform in compatible:
            return TargetKind.Rigidbody if TargetKind.Rigidbody in compatible and obj.get_component(Rigidbody) is not None else TargetKind.Transform
        candidates = [kind for kind in sorted(compatible, key=lambda kind: kind.value)
                      if kind != TargetKind.Material and obj.get_component(_TARGETS[kind]) is not None]
        if len(candidates) != 1:
            raise ValueError(f"Select Target Component for {self.animation_type.value}: {len(candidates)} suitable components on {obj.name}")
        return candidates[0]

    def _resolve_target(self, preview=False, kind=None):
        kind = self._resolve_kind() if kind is None else kind
        if kind == TargetKind.Material:
            if self.material is None:
                raise ValueError("Select the material to animate")
            return self.material
        obj = self._target_object()
        if kind == TargetKind.Transform or (preview and kind == TargetKind.Rigidbody):
            return obj.transform
        target = obj.get_component(_TARGETS[kind])
        if target is None:
            raise ValueError(f"{obj.name} needs {_TARGETS[kind].__name__}")
        return target

    def _lifetime_target(self):
        return self.game_object if self.target_kind == TargetKind.Material else self._target_object()

    def _build(self, preview=False):
        target_kind = self._resolve_kind()
        if target_kind not in _COMPATIBLE.get(self.animation_type, {TargetKind.Transform}):
            raise ValueError(f"{self.animation_type.value} does not animate {target_kind.value}")
        target, kind = self._resolve_target(preview, target_kind), self.animation_type
        shortcut = getattr(S, "DO" + kind.name)
        if kind == AnimationType.Text:
            return shortcut(target, self.end_text, self.duration, self.rich_text, self.scramble_mode,
                            self.scramble_chars, seed=self.seed)
        if kind.name.startswith("Shake"):
            return shortcut(target, self.duration, Vector3(*self.end_vector), self.vibrato, seed=self.seed)
        if kind.name.startswith("Punch"):
            return shortcut(target, Vector3(*self.end_vector), self.duration, self.vibrato)
        if kind == AnimationType.Float:
            return shortcut(target, self.end_value, self.property_name, self.duration)
        end = self.end_vector if kind in _VECTOR else (self.end_color if kind == AnimationType.Color else
              self.end_size if kind == AnimationType.Size else self.end_value)
        if target_kind == TargetKind.Material:
            return shortcut(target, end, self.duration, property=self.property_name)
        return shortcut(target, end, self.duration)

    def _after_configure(self, tween):
        if self.is_from:
            if self.animation_type.name.startswith(("Punch", "Shake")):
                raise ValueError("Punch and Shake already return to their original pose")
            tween.From(self.relative)

    def _capture_preview(self, scope):
        target_kind = self._resolve_kind()
        target, kind = self._resolve_target(True, target_kind), self.animation_type
        if target_kind == TargetKind.Material:
            scope.capture_material(target)
        elif kind in _PROPERTIES:
            scope.capture(target, _PROPERTIES[kind])
        elif kind.name.startswith(("Punch", "Shake")):
            name = {"Position": "local_position", "Rotation": "local_euler_angles", "Scale": "local_scale"}
            scope.capture(target, name[kind.name[5:]])
        elif kind == AnimationType.Color:
            scope.capture(target, {TargetKind.Sprite: "sprite_color", TargetKind.Button: "background_color",
                                   TargetKind.Camera: "background_color"}.get(target_kind, "color"))
        elif kind == AnimationType.Fade:
            scope.capture(target, {TargetKind.Sprite: "sprite_color", TargetKind.Audio: "volume", TargetKind.CanvasGroup: "alpha"}.get(target_kind, "opacity"))
        elif kind == AnimationType.Size:
            scope.capture(target, "width", "height")
        elif kind == AnimationType.Value:
            scope.capture(target, "value")
        elif kind == AnimationType.Text:
            scope.capture_text(target)
            scope.capture(target, "text", "rich_text")
