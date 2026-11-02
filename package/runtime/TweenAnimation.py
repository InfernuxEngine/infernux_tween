from enum import Enum

from infernux.components import (
    ComponentRef,
    GameObjectRef,
    FieldType,
    InxComponent,
    add_component_menu,
    serialized_field,
)
from infernux.components.builtin import (
    AudioSource,
    Camera,
    Light,
    MeshRenderer,
    Rigidbody,
    SpriteRenderer,
)
from infernux.lib import Transform, Vector2, Vector3
from infernux.screen import Rect
from infernux.ui import InxUIScreenComponent, UIButton, UIGroup, UIImage, UIProgressBar, UISlider, UIText

from infernux_tween import RotateMode, ScrambleMode, ShakeRandomnessMode, shortcuts as S
from .TweenAuthoring import TweenAuthoring, _field_alias


class AnimationType(Enum):
    NONE = 0
    MOVE = 1
    LOCAL_MOVE = 2
    ROTATE = 3
    LOCAL_ROTATE = 4
    SCALE = 5
    COLOR = 6
    FADE = 7
    TEXT = 8
    PUNCH_POSITION = 9
    PUNCH_ROTATION = 10
    PUNCH_SCALE = 11
    SHAKE_POSITION = 12
    SHAKE_ROTATION = 13
    SHAKE_SCALE = 14
    CAMERA_ASPECT = 15
    CAMERA_BACKGROUND_COLOR = 16
    CAMERA_FIELD_OF_VIEW = 17
    CAMERA_ORTHO_SIZE = 18
    CAMERA_PIXEL_RECT = 19
    CAMERA_RECT = 20
    UI_WIDTH_HEIGHT = 21
    FILL_AMOUNT = 22
    # Engine-specific authoring controls use a separate numeric range.
    VALUE = 1000
    FLOAT = 1001
    INTENSITY = 1002
    SHADOW_STRENGTH = 1003
    PITCH = 1004
    SIZE = UI_WIDTH_HEIGHT
    FIELD_OF_VIEW = CAMERA_FIELD_OF_VIEW
    ORTHO_SIZE = CAMERA_ORTHO_SIZE


class TargetType(Enum):
    UNSET = 0
    CAMERA = 1
    CANVAS_GROUP = 2
    IMAGE = 3
    LIGHT = 4
    RECT_TRANSFORM = 5
    RENDERER = 6
    SPRITE_RENDERER = 7
    RIGIDBODY = 8
    RIGIDBODY2_D = 9
    TEXT = 10
    TRANSFORM = 11
    TK2D_BASE_SPRITE = 12
    TK2D_TEXT_MESH = 13
    TEXT_MESH_PRO = 14
    TEXT_MESH_PRO_UGUI = 15


class TargetKind(Enum):
    AUTO = "Auto"
    TRANSFORM = "Transform"
    RECT_TRANSFORM = "RectTransform"
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
    RENDERER = "Renderer"


_TARGETS = {
    TargetKind.RECT_TRANSFORM: InxUIScreenComponent,
    TargetKind.RIGIDBODY: Rigidbody,
    TargetKind.TEXT: UIText,
    TargetKind.IMAGE: UIImage,
    TargetKind.BUTTON: UIButton,
    TargetKind.CANVAS_GROUP: UIGroup,
    TargetKind.SLIDER: UISlider,
    TargetKind.PROGRESS_BAR: UIProgressBar,
    TargetKind.SPRITE: SpriteRenderer,
    TargetKind.LIGHT: Light,
    TargetKind.CAMERA: Camera,
    TargetKind.AUDIO: AudioSource,
    TargetKind.RENDERER: MeshRenderer,
}
_VECTOR = {
    AnimationType[name]
    for name in (
        "MOVE",
        "LOCAL_MOVE",
        "ROTATE",
        "LOCAL_ROTATE",
        "SCALE",
        "PUNCH_POSITION",
        "PUNCH_ROTATION",
        "PUNCH_SCALE",
        "SHAKE_POSITION",
        "SHAKE_ROTATION",
        "SHAKE_SCALE",
    )
}
_CAMERA_SHORTCUTS = {
    AnimationType.CAMERA_ASPECT: "twn_aspect",
    AnimationType.CAMERA_BACKGROUND_COLOR: "twn_color",
    AnimationType.CAMERA_FIELD_OF_VIEW: "twn_field_of_view",
    AnimationType.CAMERA_ORTHO_SIZE: "twn_ortho_size",
    AnimationType.CAMERA_PIXEL_RECT: "twn_pixel_rect",
    AnimationType.CAMERA_RECT: "twn_rect",
}
_SHORTCUTS = {
    kind: getattr(
        S,
        _CAMERA_SHORTCUTS.get(
            kind,
            (
                "twn_size_delta"
                if kind == AnimationType.SIZE
                else "twn_" + kind.name.lower()
            ),
        ),
    )
    for kind in AnimationType
    if kind != AnimationType.NONE
}
_PROPERTIES = {
    AnimationType.MOVE: "position",
    AnimationType.LOCAL_MOVE: "local_position",
    AnimationType.ROTATE: "euler_angles",
    AnimationType.LOCAL_ROTATE: "local_euler_angles",
    AnimationType.SCALE: "local_scale",
    AnimationType.FIELD_OF_VIEW: "field_of_view",
    AnimationType.ORTHO_SIZE: "orthographic_size",
    AnimationType.INTENSITY: "intensity",
    AnimationType.SHADOW_STRENGTH: "shadow_strength",
    AnimationType.PITCH: "pitch",
}
_PROPERTIES.update(
    {
        AnimationType.CAMERA_ASPECT: "aspect_ratio",
        AnimationType.CAMERA_BACKGROUND_COLOR: "background_color",
        AnimationType.CAMERA_PIXEL_RECT: "pixel_rect",
        AnimationType.CAMERA_RECT: "rect",
    }
)
_COMPATIBLE = {
    AnimationType.MOVE: {TargetKind.TRANSFORM, TargetKind.RIGIDBODY, TargetKind.RECT_TRANSFORM},
    AnimationType.ROTATE: {TargetKind.TRANSFORM, TargetKind.RIGIDBODY},
    AnimationType.COLOR: {
        TargetKind.TEXT,
        TargetKind.IMAGE,
        TargetKind.BUTTON,
        TargetKind.SPRITE,
        TargetKind.LIGHT,
        TargetKind.CAMERA,
        TargetKind.MATERIAL,
        TargetKind.RENDERER,
    },
    AnimationType.FADE: {
        TargetKind.TEXT,
        TargetKind.IMAGE,
        TargetKind.BUTTON,
        TargetKind.SPRITE,
        TargetKind.CANVAS_GROUP,
        TargetKind.AUDIO,
        TargetKind.LIGHT,
        TargetKind.MATERIAL,
        TargetKind.RENDERER,
    },
    AnimationType.VALUE: {TargetKind.SLIDER, TargetKind.PROGRESS_BAR},
    AnimationType.SIZE: {TargetKind.TEXT, TargetKind.IMAGE, TargetKind.BUTTON, TargetKind.RECT_TRANSFORM},
    AnimationType.PUNCH_POSITION: {TargetKind.TRANSFORM, TargetKind.RECT_TRANSFORM},
    AnimationType.SHAKE_POSITION: {TargetKind.TRANSFORM, TargetKind.RECT_TRANSFORM},
    AnimationType.FLOAT: {TargetKind.MATERIAL},
    AnimationType.FIELD_OF_VIEW: {TargetKind.CAMERA},
    AnimationType.ORTHO_SIZE: {TargetKind.CAMERA},
    AnimationType.INTENSITY: {TargetKind.LIGHT},
    AnimationType.SHADOW_STRENGTH: {TargetKind.LIGHT},
    AnimationType.PITCH: {TargetKind.AUDIO},
    AnimationType.TEXT: {TargetKind.TEXT},
    AnimationType.FILL_AMOUNT: {TargetKind.IMAGE},
}
_COMPATIBLE.update({kind: {TargetKind.CAMERA} for kind in _CAMERA_SHORTCUTS})
_TARGET_KINDS = {
    TargetType.RECT_TRANSFORM: TargetKind.RECT_TRANSFORM,
    TargetType.TRANSFORM: TargetKind.TRANSFORM,
    TargetType.RIGIDBODY: TargetKind.RIGIDBODY,
    TargetType.RENDERER: TargetKind.RENDERER,
    TargetType.CAMERA: TargetKind.CAMERA,
    TargetType.LIGHT: TargetKind.LIGHT,
    TargetType.IMAGE: TargetKind.IMAGE,
    TargetType.CANVAS_GROUP: TargetKind.CANVAS_GROUP,
    TargetType.SPRITE_RENDERER: TargetKind.SPRITE,
    TargetType.TEXT: TargetKind.TEXT,
    TargetType.TEXT_MESH_PRO: TargetKind.TEXT,
    TargetType.TEXT_MESH_PRO_UGUI: TargetKind.TEXT,
}


_SNAPPING = {
    AnimationType.MOVE,
    AnimationType.LOCAL_MOVE,
    AnimationType.PUNCH_POSITION,
    AnimationType.SHAKE_POSITION,
}
_UNIFORM = {AnimationType.SCALE, AnimationType.SIZE}
_GO_TRANSFORM = {
    AnimationType.LOCAL_MOVE,
    AnimationType.LOCAL_ROTATE,
    AnimationType.SCALE,
    AnimationType.PUNCH_ROTATION,
    AnimationType.PUNCH_SCALE,
    AnimationType.SHAKE_ROTATION,
    AnimationType.SHAKE_SCALE,
}
_ENGINE_TARGET_KINDS = {
    TargetKind.MATERIAL,
    TargetKind.AUDIO,
    TargetKind.BUTTON,
    TargetKind.SLIDER,
    TargetKind.PROGRESS_BAR,
}
_RECT_ANIMATIONS = frozenset({AnimationType.MOVE, AnimationType.SIZE,
                             AnimationType.PUNCH_POSITION, AnimationType.SHAKE_POSITION})


@add_component_menu("Animation/Tween Animation")
class TweenAnimation(TweenAuthoring):
    AnimationType = AnimationType
    TargetType = TargetType
    target: ComponentRef = serialized_field(
        default=None,
        field_type=FieldType.COMPONENT,
        display_name_key="tween.target_component",
    )
    target_is_self: bool = serialized_field(
        default=True, display_name_key="tween.target_is_self"
    )
    target_go: GameObjectRef = serialized_field(
        default=None,
        field_type=FieldType.GAME_OBJECT,
        display_name_key="tween.target_go",
        visible_when=lambda c: not c.target_is_self,
    )
    tween_target_is_target_go: bool = serialized_field(
        default=True,
        display_name_key="tween.group_uses_target",
        visible_when=lambda c: not c.target_is_self,
    )
    is_active: bool = serialized_field(
        default=True, display_name_key="tween.animation_active"
    )
    # Component lifetime and authoring validity have independent flags.
    animation_valid: bool = serialized_field(default=False, hidden=True)
    target_type: TargetType = serialized_field(default=TargetType.UNSET, hidden=True)
    forced_target_type: TargetType = serialized_field(
        default=TargetType.UNSET,
        display_name_key="tween.forced_target_type",
        enum_labels=["tween.target_type." + e.name for e in TargetType],
    )
    animation_type: AnimationType = serialized_field(
        default=AnimationType.NONE,
        display_name_key="tween.animation_type",
        enum_labels=["tween.animation." + e.name for e in AnimationType],
    )
    target_kind: TargetKind = serialized_field(
        default=TargetKind.AUTO,
        display_name_key="tween.target_kind",
        enum_labels=["tween.target_kind." + e.name for e in TargetKind],
    )
    material = serialized_field(
        default=None,
        field_type=FieldType.MATERIAL,
        display_name_key="tween.material",
        visible_when=lambda c: c.target_kind == TargetKind.MATERIAL,
    )
    end_vector = serialized_field(
        default=(0.0, 0.0, 0.0),
        field_type=FieldType.VEC3,
        display_name_key="tween.end_vector",
        visible_when=lambda c: c.animation_type in _VECTOR
        and not (c.animation_type == AnimationType.SCALE and c.optional_bool0),
    )
    end_color = serialized_field(
        default=[1.0, 1.0, 1.0, 1.0],
        field_type=FieldType.COLOR,
        display_name_key="tween.end_color",
        visible_when=lambda c: c.animation_type
        in (AnimationType.COLOR, AnimationType.CAMERA_BACKGROUND_COLOR),
    )
    end_size = serialized_field(
        default=(0.0, 0.0),
        field_type=FieldType.VEC2,
        display_name_key="tween.end_size",
        visible_when=lambda c: c.animation_type == AnimationType.SIZE
        and not c.optional_bool0,
    )
    end_value: float = serialized_field(
        default=0.0,
        display_name_key="tween.end_value",
        visible_when=lambda c: c.animation_type
        not in _VECTOR | {AnimationType.COLOR, AnimationType.SIZE, AnimationType.TEXT}
        or c.animation_type in _UNIFORM
        and c.optional_bool0,
    )
    end_text: str = serialized_field(
        default="",
        multiline=True,
        display_name_key="tween.end_text",
        visible_when=lambda c: c.animation_type == AnimationType.TEXT,
    )
    optional_bool0: bool = serialized_field(default=False, hidden=True)
    optional_bool1: bool = serialized_field(
        default=False,
        display_name_key="tween.fade_out",
        visible_when=lambda c: c.animation_type.name.startswith("SHAKE_"),
    )
    optional_rotation_mode: RotateMode = serialized_field(
        default=RotateMode.FAST,
        display_name_key="tween.rotation_mode",
        enum_labels=["tween.rotation_mode." + e.name for e in RotateMode],
        visible_when=lambda c: c.animation_type
        in (AnimationType.ROTATE, AnimationType.LOCAL_ROTATE),
    )
    optional_scramble_mode: ScrambleMode = serialized_field(
        default=ScrambleMode.NONE,
        display_name_key="tween.scramble_mode",
        enum_labels=["tween.scramble." + e.name for e in ScrambleMode],
        visible_when=lambda c: c.animation_type == AnimationType.TEXT,
    )
    optional_string: str = serialized_field(
        default="",
        display_name_key="tween.scramble_chars",
        visible_when=lambda c: c.animation_type == AnimationType.TEXT
        and c.optional_scramble_mode == ScrambleMode.CUSTOM,
    )
    property_name: str = serialized_field(
        default="baseColor",
        display_name_key="tween.material_property",
        visible_when=lambda c: c.target_kind == TargetKind.MATERIAL,
    )
    optional_int0: int = serialized_field(
        default=0,
        range=(1, 100),
        slider=False,
        display_name_key="tween.vibrato",
        visible_when=lambda c: c.animation_type.name.startswith(("PUNCH_", "SHAKE_")),
    )
    optional_float0: float = serialized_field(default=0.0, hidden=True)
    optional_shake_randomness_mode: ShakeRandomnessMode = serialized_field(
        default=ShakeRandomnessMode.FULL,
        display_name_key="tween.randomness_mode",
        enum_labels=["tween.randomness_mode." + e.name for e in ShakeRandomnessMode],
        visible_when=lambda c: c.animation_type.name.startswith("SHAKE_"),
    )
    is_from: bool = serialized_field(
        default=False,
        display_name_key="tween.from",
        visible_when=lambda c: not c.animation_type.name.startswith(
            ("PUNCH_", "SHAKE_")
        ),
    )
    use_target_as_v3: bool = serialized_field(
        default=False,
        display_name_key="tween.use_end_transform",
        visible_when=lambda c: c.animation_type == AnimationType.MOVE,
    )
    _end_transform: GameObjectRef = serialized_field(
        default=None,
        field_type=FieldType.GAME_OBJECT,
        display_name_key="tween.end_transform",
        visible_when=lambda c: c.use_target_as_v3,
    )
    _end_rect: tuple = serialized_field(
        default=(0.0, 0.0, 0.0, 0.0),
        field_type=FieldType.VEC4,
        display_name_key="tween.end_rect",
        visible_when=lambda c: c.animation_type
        in (AnimationType.CAMERA_RECT, AnimationType.CAMERA_PIXEL_RECT),
    )

    end_value_float = _field_alias("end_value")
    end_value_v3 = _field_alias("end_vector")
    end_value_v2 = _field_alias("end_size")
    end_value_color = _field_alias("end_color")
    end_value_string = _field_alias("end_text")

    @property
    def end_value_rect(self):
        return Rect(*self._end_rect)

    @end_value_rect.setter
    def end_value_rect(self, value):
        if not isinstance(value, Rect):
            raise TypeError("end_value_rect must be Rect")
        self._end_rect = (value.x, value.y, value.width, value.height)

    @property
    def end_value_transform(self):
        return None if self._end_transform is None else self._end_transform.transform

    @end_value_transform.setter
    def end_value_transform(self, value):
        if value is not None and not isinstance(value, Transform):
            raise TypeError("end_value_transform must be Transform or None")
        self._end_transform = None if value is None else value.game_object

    @staticmethod
    def type_to_target_type(t: type) -> TargetType:
        if not isinstance(t, type):
            raise TypeError("Expected a component type")
        for base, result in (
            (Transform, TargetType.TRANSFORM),
            (Camera, TargetType.CAMERA),
            (Light, TargetType.LIGHT),
            (SpriteRenderer, TargetType.SPRITE_RENDERER),
            (MeshRenderer, TargetType.RENDERER),
            (Rigidbody, TargetType.RIGIDBODY),
            (UIImage, TargetType.IMAGE),
            (UIText, TargetType.TEXT),
            (UIGroup, TargetType.CANVAS_GROUP),
            (InxUIScreenComponent, TargetType.RECT_TRANSFORM),
        ):
            if issubclass(t, base):
                return result
        raise ValueError(f"No animation target type for {t.__name__}")

    def _target_type_for(self, target):
        if isinstance(target, InxUIScreenComponent) and self.animation_type in _RECT_ANIMATIONS:
            return TargetType.RECT_TRANSFORM
        return self.type_to_target_type(type(target))

    def _target_object(self):
        return self.game_object if self.target_is_self else self.target_go

    def awake(self):
        if not (self.animation_type == AnimationType.MOVE and self.use_target_as_v3):
            self._auto_generate()

    def start(self):
        self._auto_generate()

    def on_enable(self):
        # Generation belongs to Awake/Start, not repeated pool activation.
        pass

    def _auto_generate(self):
        if self.is_active:
            super().on_enable()

    def _create_tween(self, *args, **kwargs):
        if not self.animation_valid:
            return None
        return super()._create_tween(*args, **kwargs)

    def _resolve_kind(self):
        selected = self.forced_target_type
        if selected == TargetType.UNSET and self.target_kind != TargetKind.AUTO:
            return self.target_kind
        if selected == TargetType.UNSET:
            selected = self.target_type
        if selected != TargetType.UNSET:
            if selected not in _TARGET_KINDS:
                raise ValueError(
                    f"The engine does not yet provide animation target type {selected.name}"
                )
            return _TARGET_KINDS[selected]
        if self.target is not None:
            return _TARGET_KINDS[self.type_to_target_type(type(self.target))]
        compatible = _COMPATIBLE.get(self.animation_type, {TargetKind.TRANSFORM})
        obj = self._target_object()
        if TargetKind.RIGIDBODY in compatible and obj.get_component(Rigidbody) is not None:
            return TargetKind.RIGIDBODY
        if TargetKind.RECT_TRANSFORM in compatible and obj.get_component(InxUIScreenComponent) is not None:
            return TargetKind.RECT_TRANSFORM
        if TargetKind.TRANSFORM in compatible:
            return (
                TargetKind.RIGIDBODY
                if TargetKind.RIGIDBODY in compatible
                and obj.get_component(Rigidbody) is not None
                else TargetKind.TRANSFORM
            )
        candidates = [
            kind
            for kind in sorted(compatible, key=lambda kind: kind.value)
            if kind != TargetKind.MATERIAL
            and obj.get_component(_TARGETS[kind]) is not None
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Select Target Component for {self.animation_type.value}: {len(candidates)} suitable components on {obj.name}"
            )
        return candidates[0]

    def _resolve_target(self, preview=False, kind=None):
        if self.animation_type in _GO_TRANSFORM:
            return self._target_object().transform
        kind = self._resolve_kind() if kind is None else kind
        if kind == TargetKind.MATERIAL:
            if self.material is None:
                raise ValueError("Select the material to animate")
            return self.material
        if self.target is not None:
            target = self.target
            return (
                target.transform
                if preview and isinstance(target, Rigidbody)
                else target
            )
        obj = self._target_object()
        if kind == TargetKind.TRANSFORM or (preview and kind == TargetKind.RIGIDBODY):
            return obj.transform
        target = obj.get_component(_TARGETS[kind])
        if target is None:
            raise ValueError(f"{obj.name} needs {_TARGETS[kind].__name__}")
        return target

    def set_animation_target(
        self,
        tween_target: InxComponent | Transform,
        use_tween_target_game_object_for_group_operations: bool = True,
    ) -> None:
        if self.target is None:
            return None
        if self._target_type_for(self.target) != self.target_type:
            return None
        self.target = tween_target
        self.target_go = tween_target.game_object
        self.tween_target_is_target_go = bool(
            use_tween_target_game_object_for_group_operations
        )

    def _group_target(self):
        return (
            self.game_object
            if self.target_is_self or not self.tween_target_is_target_go
            else self.target_go
        )

    def _restart_from_here(self):
        kind = self.animation_type
        if kind in (AnimationType.MOVE, AnimationType.LOCAL_MOVE):
            target = self._resolve_target()
            prop = 'anchored_position3d' if kind == AnimationType.MOVE and self._resolve_kind() == TargetKind.RECT_TRANSFORM else _PROPERTIES[kind]
            start = getattr(target, prop)
            self._tween.change_values(start, start + Vector3(*self.end_vector))

    def _lifetime_target(self):
        return (
            self.game_object
            if self.target_kind == TargetKind.MATERIAL
            else self._target_object()
        )

    def on_validate(self):
        super().on_validate()
        from infernux.lib import SceneManager

        if SceneManager.instance().is_playing():
            return
        if self.animation_type == AnimationType.NONE:
            self.animation_valid = False
            return
        try:
            if self.target_kind == TargetKind.MATERIAL:
                self._resolve_target()
                self.animation_valid = (
                    self.animation_type in _SHORTCUTS
                    and self.target_kind in _COMPATIBLE.get(self.animation_type, set())
                )
                return
            if self.target is None:
                self.target = self._resolve_target()
            if self.target_kind not in _ENGINE_TARGET_KINDS:
                self.target_type = self._target_type_for(self.target)
            if self.forced_target_type != TargetType.UNSET:
                self.target_type = self.forced_target_type
            kind = (
                TargetKind.TRANSFORM
                if self.animation_type in _GO_TRANSFORM
                else self._resolve_kind()
            )
            self.animation_valid = (
                kind in _COMPATIBLE.get(self.animation_type, {TargetKind.TRANSFORM})
                and self.animation_type in _SHORTCUTS
            )
        except (TypeError, ValueError, AttributeError):
            self.animation_valid = False

    def _configure_relative(self, tween):
        if not self.is_from:
            super()._configure_relative(tween)

    def _build(self, preview=False):
        if (
            (self.target is None and self.target_kind != TargetKind.MATERIAL)
            or self._target_object() is None
            or self.animation_type == AnimationType.NONE
        ):
            return None
        if self.forced_target_type != TargetType.UNSET:
            self.target_type = self.forced_target_type
        elif (
            self.target_type == TargetType.UNSET
            and self.target_kind not in _ENGINE_TARGET_KINDS
        ):
            self.target_type = self._target_type_for(self.target)
        target_kind = (
            TargetKind.TRANSFORM
            if self.animation_type in _GO_TRANSFORM
            else self._resolve_kind()
        )
        if target_kind not in _COMPATIBLE.get(
            self.animation_type, {TargetKind.TRANSFORM}
        ):
            return None
        target, kind = self._resolve_target(preview, target_kind), self.animation_type
        if kind in (AnimationType.COLOR, AnimationType.FADE):
            self.relative = False
        if kind == AnimationType.MOVE and self.use_target_as_v3:
            self.relative = False
            end = self.end_value_transform
            self.end_vector = (0.0, 0.0, 0.0) if end is None else tuple(end.position)
        if kind in (AnimationType.CAMERA_RECT, AnimationType.CAMERA_PIXEL_RECT):
            return _SHORTCUTS[kind](target, self.end_value_rect, self.duration)
        if kind == AnimationType.CAMERA_BACKGROUND_COLOR:
            return _SHORTCUTS[kind](target, self.end_color, self.duration)
        if kind == AnimationType.FADE and target_kind == TargetKind.LIGHT:
            return S.twn_intensity(target, self.end_value_float, self.duration)
        if target_kind == TargetKind.RENDERER:
            material = target.material
            if material is None:
                raise ValueError("Renderer animation requires a material in slot zero")
            if kind == AnimationType.COLOR:
                return S.twn_color(material, self.end_value_color, self.duration)
            return S.twn_fade(material, self.end_value_float, self.duration)
        if target_kind == TargetKind.RECT_TRANSFORM:
            if kind == AnimationType.MOVE:
                return S.twn_anchor_pos3d(target, Vector3(*self.end_vector), self.duration, self.optional_bool0)
            if kind == AnimationType.PUNCH_POSITION:
                end = self.end_vector
                return S.twn_punch_anchor_pos(target, Vector2(end.x, end.y), self.duration,
                    self.optional_int0, self.optional_float0, self.optional_bool0)
            if kind == AnimationType.SHAKE_POSITION:
                end = self.end_vector
                return S.twn_shake_anchor_pos(target, self.duration, Vector2(end.x, end.y),
                    self.optional_int0, self.optional_float0, self.optional_bool0, self.optional_bool1,
                    self.optional_shake_randomness_mode)
        shortcut = _SHORTCUTS[kind]
        if kind == AnimationType.TEXT:
            return shortcut(
                target,
                self.end_text,
                self.duration,
                self.optional_bool0,
                self.optional_scramble_mode,
                self.optional_string or None,
            )
        if kind.name.startswith("SHAKE_"):
            options = dict(
                vibrato=self.optional_int0,
                randomness=self.optional_float0,
                fade_out=self.optional_bool1,
                randomness_mode=self.optional_shake_randomness_mode,
            )
            if kind == AnimationType.SHAKE_POSITION:
                options["snapping"] = self.optional_bool0
            return shortcut(target, self.duration, Vector3(*self.end_vector), **options)
        if kind.name.startswith("PUNCH_"):
            options = dict(vibrato=self.optional_int0, elasticity=self.optional_float0)
            if kind == AnimationType.PUNCH_POSITION:
                options["snapping"] = self.optional_bool0
            return shortcut(target, Vector3(*self.end_vector), self.duration, **options)
        if kind == AnimationType.FLOAT:
            return shortcut(target, self.end_value, self.property_name, self.duration)
        end = (
            self.end_vector
            if kind in _VECTOR
            else (
                self.end_color
                if kind == AnimationType.COLOR
                else self.end_size if kind == AnimationType.SIZE else self.end_value
            )
        )
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
            tween.from_(self.relative)

    def _capture_preview(self, scope):
        if not self.animation_valid or self.animation_type == AnimationType.NONE:
            return
        target_kind = (
            TargetKind.TRANSFORM
            if self.animation_type in _GO_TRANSFORM
            else self._resolve_kind()
        )
        target, kind = self._resolve_target(True, target_kind), self.animation_type
        if target_kind == TargetKind.RECT_TRANSFORM and kind in _RECT_ANIMATIONS:
            scope.capture_rect_transform(target)
        elif target_kind == TargetKind.RENDERER:
            scope.capture_renderer_material(target)
        elif target_kind == TargetKind.MATERIAL:
            scope.capture_material(target)
        elif kind in _PROPERTIES:
            scope.capture(target, _PROPERTIES[kind])
        elif kind.name.startswith(("PUNCH_", "SHAKE_")):
            name = {
                "POSITION": "local_position",
                "ROTATION": "local_euler_angles",
                "SCALE": "local_scale",
            }
            scope.capture(target, name[kind.name.split("_", 1)[1]])
        elif kind == AnimationType.COLOR:
            scope.capture(
                target,
                {
                    TargetKind.SPRITE: "sprite_color",
                    TargetKind.BUTTON: "background_color",
                    TargetKind.CAMERA: "background_color",
                }.get(target_kind, "color"),
            )
        elif kind == AnimationType.FADE:
            scope.capture(
                target,
                {
                    TargetKind.SPRITE: "sprite_color",
                    TargetKind.AUDIO: "volume",
                    TargetKind.LIGHT: "intensity",
                    TargetKind.CANVAS_GROUP: "alpha",
                    TargetKind.BUTTON: "background_color",
                }.get(target_kind, "color"),
            )
        elif kind == AnimationType.SIZE:
            scope.capture_rect_transform(target)
        elif kind == AnimationType.FILL_AMOUNT:
            scope.capture(target, "fill_amount")
        elif kind == AnimationType.VALUE:
            scope.capture(target, "value")
        elif kind == AnimationType.TEXT:
            scope.capture_text(target)
            scope.capture(target, "text", "rich_text")
