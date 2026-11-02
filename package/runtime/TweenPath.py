from infernux.components import (
    FieldType,
    GameObjectRef,
    add_component_menu,
    serialized_field,
)
from infernux.components.builtin import Rigidbody
from infernux.lib import Transform, Vector3, quatf

from infernux_tween import (
    AxisConstraint,
    HandlesDrawMode,
    HandlesType,
    OrientType,
    Path,
    PathMode,
    PathType,
    TweenInspectorMode,
    shortcuts as S,
)
from .TweenAuthoring import TweenAuthoring, _field_alias

_UNSET_PATH = object()


@add_component_menu("Animation/Tween Path")
class TweenPath(TweenAuthoring):
    _draw_key = None
    _draw_points = ()
    _world_draw_key = None
    _world_draw_points = ()
    _runtime_path = None
    _runtime_tween = None
    _drawing_path_key = None
    _drawing_path_cache = None

    def get_tween(self):
        return self.tween

    inspector_mode: TweenInspectorMode = serialized_field(
        default=TweenInspectorMode.DEFAULT, display_name_key="tween.inspector_mode",
        enum_labels=["tween.inspector_mode." + value.name for value in TweenInspectorMode],
    )
    handles_type: HandlesType = serialized_field(
        default=HandlesType.FREE, display_name_key="tween.handles_type",
        enum_labels=["tween.handles_type." + value.name for value in HandlesType],
    )
    live_preview: bool = serialized_field(default=True, display_name_key="tween.live_preview")
    handles_draw_mode: HandlesDrawMode = serialized_field(
        default=HandlesDrawMode.ORTHOGRAPHIC, display_name_key="tween.handles_draw_mode",
        enum_labels=["tween.handles_draw_mode." + value.name for value in HandlesDrawMode],
    )
    perspective_handle_size: float = serialized_field(
        default=.5, range=(.001, 10), slider=False, display_name_key="tween.perspective_handle_size",
        visible_when=lambda c: c.handles_draw_mode == HandlesDrawMode.PERSPECTIVE,
    )
    show_indexes: bool = serialized_field(default=True, display_name_key="tween.show_indexes")
    show_wp_length: bool = serialized_field(default=False, display_name_key="tween.show_wp_length")
    wps_dropdown: bool = serialized_field(default=False, hidden=True)
    drop_to_floor_offset: float = serialized_field(default=0.0, display_name_key="tween.drop_to_floor_offset")

    def on_enable(self):
        from infernux.lib import SceneManager
        if SceneManager.instance().is_playing() and self.inspector_mode == TweenInspectorMode.ONLY_PATH:
            self._auto_generation_called = True
            return
        super().on_enable()

    waypoints: list = serialized_field(
        default=[(0.0, 1.0, 0.0)],
        field_type=FieldType.LIST,
        element_type=FieldType.VEC3,
        display_name_key="tween.waypoints",
    )
    path_type: PathType = serialized_field(
        default=PathType.LINEAR,
        display_name_key="tween.path_type",
        enum_labels=["tween.path_type." + e.name for e in PathType],
    )
    path_mode: PathMode = serialized_field(
        default=PathMode.FULL3_D,
        display_name_key="tween.path_mode",
        enum_labels=["tween.path_mode." + e.name for e in PathMode],
    )
    resolution: int = serialized_field(
        default=10, range=(1, 100), slider=False, display_name_key="tween.resolution"
    )
    local: bool = serialized_field(default=False, display_name_key="tween.local")
    close_path: bool = serialized_field(
        default=False, display_name_key="tween.close_path"
    )
    use_rigidbody: bool = serialized_field(
        default=False, display_name_key="tween.use_rigidbody"
    )
    orient_type: OrientType = serialized_field(
        default=OrientType.NONE,
        display_name_key="tween.orient_type",
        enum_labels=["tween.orient_type." + value.name for value in OrientType],
    )
    look_ahead: float = serialized_field(
        default=0.01,
        range=(0.001, 1),
        display_name_key="tween.look_ahead",
        visible_when=lambda c: c.orient_type == OrientType.TO_PATH,
    )
    look_at_target: GameObjectRef = serialized_field(
        default=None,
        field_type=FieldType.GAME_OBJECT,
        display_name_key="tween.look_at_target",
        visible_when=lambda c: c.orient_type == OrientType.LOOK_AT_TRANSFORM,
    )
    look_at_position: tuple = serialized_field(
        default=(0.0, 0.0, 0.0),
        field_type=FieldType.VEC3,
        display_name_key="tween.look_at_position",
        visible_when=lambda c: c.orient_type == OrientType.LOOK_AT_POSITION,
    )
    lock_rotation: AxisConstraint = serialized_field(
        default=AxisConstraint.NONE, display_name_key="tween.lock_rotation"
    )
    assign_forward_and_up: bool = serialized_field(
        default=False, display_name_key="tween.assign_forward_and_up"
    )
    forward_direction: tuple = serialized_field(
        default=(0.0, 0.0, 1.0),
        field_type=FieldType.VEC3,
        display_name_key="tween.forward_direction",
        visible_when=lambda c: c.assign_forward_and_up,
    )
    up_direction: tuple = serialized_field(
        default=(0.0, 1.0, 0.0),
        field_type=FieldType.VEC3,
        display_name_key="tween.up_direction",
        visible_when=lambda c: c.assign_forward_and_up,
    )
    path_color: list = serialized_field(
        default=[1.0, 1.0, 1.0, 0.5],
        field_type=FieldType.COLOR,
        display_name_key="tween.path_color",
    )
    full_wps: list = serialized_field(
        default=[], field_type=FieldType.LIST, element_type=FieldType.VEC3, hidden=True
    )
    last_src_position: tuple = serialized_field(
        default=(0.0, 0.0, 0.0), field_type=FieldType.VEC3, hidden=True
    )
    _last_src_rotation: tuple = serialized_field(
        default=(0.0, 0.0, 0.0, 0.0), field_type=FieldType.VEC4, hidden=True
    )
    _baked_path = _UNSET_PATH
    _path_source_key = None
    _path_source = None

    wps = _field_alias("waypoints")
    path_resolution = _field_alias("resolution")
    is_local = _field_alias("local")
    is_closed_path = _field_alias("close_path")
    tween_rigidbody = _field_alias("use_rigidbody")

    @property
    def orient_to_path(self):
        return self.orient_type == OrientType.TO_PATH

    @orient_to_path.setter
    def orient_to_path(self, value):
        self.orient_type = OrientType.TO_PATH if value else OrientType.NONE

    @property
    def look_at_transform(self):
        target = self.look_at_target
        return None if target is None else target.transform

    @look_at_transform.setter
    def look_at_transform(self, value):
        if value is not None and not isinstance(value, Transform):
            raise TypeError("look_at_transform must be Transform or None")
        self.look_at_target = None if value is None else value.game_object

    @property
    def last_src_rotation(self):
        return quatf(*self._last_src_rotation)

    @last_src_rotation.setter
    def last_src_rotation(self, value):
        self._last_src_rotation = value

    @property
    def path(self):
        if self._runtime_tween is not None and self._runtime_tween._path is not None:
            return self._runtime_tween._path
        return self._runtime_path or self._authored_path()

    def _authored_path(self):
        if self._baked_path is not _UNSET_PATH:
            return self._baked_path
        if not self.full_wps:
            return None
        key = (
            tuple(tuple(point) for point in self.full_wps),
            self.path_type,
            self.resolution,
            self.close_path,
        )
        if key != self._path_source_key:
            self._path_source = Path(
                self.full_wps[0],
                self.full_wps[1:],
                self.path_type,
                self.resolution,
                self.close_path,
            )
            self._path_source_key = key
        return self._path_source

    @path.setter
    def path(self, value):
        if value is not None and not isinstance(value, Path):
            raise TypeError("path must be a compiled Path or None")
        self._baked_path = value
        self._path_source_key = None
        self._runtime_tween = self._runtime_path = None

    def _invalidate_authored_path(self):
        self._baked_path = _UNSET_PATH
        self._path_source_key = None
        self._runtime_tween = self._runtime_path = None

    def bake_path(self):
        """Capture an authored world-space route for later runtime playback."""
        target = self._target_object().transform
        self.full_wps = [
            tuple(target.position),
            *(tuple(point) for point in self.waypoints),
        ]
        self.last_src_position = tuple(target.position)
        self.last_src_rotation = tuple(target.rotation)
        self._baked_path = _UNSET_PATH
        self._path_source_key = None
        self._runtime_tween = self._runtime_path = None
        return self.path

    def _build(self, preview=False):
        obj = self._target_object()
        target = obj.transform
        if self.use_rigidbody and not preview:
            target = obj.get_component(Rigidbody)
            if target is None:
                raise ValueError(f"{obj.name} needs a Rigidbody")
        shortcut = S.twn_local_path if self.local else S.twn_path
        tween = shortcut(
            target,
            self.waypoints,
            self.duration,
            self.path_type,
            self.path_mode,
            self.resolution,
            gizmo_color=self.path_color,
        )
        tween.set_options(self.close_path, AxisConstraint.NONE, self.lock_rotation)
        source = self._authored_path()
        if source is not None:
            transform = obj.transform
            offset = (
                transform.position - Vector3(*self.last_src_position)
                if self.relative
                else Vector3(0, 0, 0)
            )
            if self.local and transform.parent is not None:
                # Pro's serialized component removes the parent's translation
                # from its baked route. The parent still supplies rotation and
                # scale when local_position is applied; ordinary local-path
                # shortcuts continue to consume local control points directly.
                offset -= transform.parent.position
            points = [point + offset for point in source.points]
            tween._compiled_path = Path(
                points[0], points[1:], source.kind, source.resolution, source.closed
            )
        look = {
            OrientType.TO_PATH: lambda: self.look_ahead,
            OrientType.LOOK_AT_POSITION: lambda: Vector3(*self.look_at_position),
            OrientType.LOOK_AT_TRANSFORM: lambda: self.look_at_transform,
        }.get(self.orient_type)
        if look is not None:
            direction = look()
            if direction is not None:
                options = (
                    dict(
                        forward_direction=Vector3(*self.forward_direction),
                        up=Vector3(*self.up_direction),
                    )
                    if self.assign_forward_and_up
                    else {}
                )
                tween.set_look_at(direction, **options)
        self._runtime_tween, self._runtime_path = tween, tween._compiled_path
        return tween

    def _deserialize_fields_document(self, data, **kwargs):
        data = dict(data)
        old_orientation = data.pop("orient_to_path", None)
        if "last_src_rotation" in data:
            data.setdefault("_last_src_rotation", data.pop("last_src_rotation"))
        recipe = data.pop("path", _UNSET_PATH)
        result = super()._deserialize_fields_document(data, **kwargs)
        if old_orientation is not None and "orient_type" not in data:
            self.orient_to_path = old_orientation
        if recipe is _UNSET_PATH:
            self._baked_path = _UNSET_PATH
            self._runtime_tween = self._runtime_path = None
            self._path_source_key = None
        else:
            self.path = (
                None
                if recipe is None
                else Path(
                    recipe["points"][0],
                    recipe["points"][1:],
                    PathType(recipe["type"]),
                    recipe["resolution"],
                    recipe["closed"],
                )
            )
        return result

    def _serialize_fields_document(self, **kwargs):
        data = super()._serialize_fields_document(**kwargs)
        if self._baked_path is not _UNSET_PATH:
            source = self._baked_path
            data["path"] = (
                None
                if source is None
                else dict(
                    points=[list(point) for point in source.points],
                    type=source.kind.value,
                    resolution=source.resolution,
                    closed=source.closed,
                )
            )
        return data

    def _capture_preview(self, scope):
        target = self._target_object().transform
        scope.capture(
            target,
            "local_position" if self.local else "position",
            "local_rotation" if self.local else "rotation",
        )

    def world_waypoint(self, index):
        target = self._target_object().transform
        point = Vector3(*self.waypoints[index])
        if self.full_wps:
            return point  # Serialized Pro authoring waypoints are world-space.
        if self.relative:
            point += target.local_position if self.local else target.position
        if self.local and target.parent is not None:
            point = target.parent.transform_point(point)
        return point

    def _restart_from_here(self):
        tween = self.tween
        tween.force_init()
        target = (
            tween._path_target.transform
            if tween.local and tween._body
            else tween._path_target
        )
        offset = getattr(target, tween._name) - tween._origin
        tween._path._translate(offset)
        tween._origin += offset
        tween._path._reset_incremental_path()

    def waypoint_from_world(self, point):
        target = self._target_object().transform
        point = Vector3(*point)
        if self.full_wps:
            return tuple(point)
        if self.local and target.parent is not None:
            point = target.parent.inverse_transform_point(point)
        if self.relative:
            point -= target.local_position if self.local else target.position
        return tuple(point)

    def _drawing_path(self):
        source = self.path
        if source is not None:
            return source
        target = self._target_object().transform
        start = target.local_position if self.local else target.position
        points = [Vector3(*p) + start if self.relative else Vector3(*p)
                  for p in self.waypoints]
        if not points:
            return None
        key = (tuple(start), tuple(tuple(p) for p in points), self.path_type,
               self.resolution, self.close_path)
        if key != self._drawing_path_key:
            self._drawing_path_cache = Path(start, points, self.path_type,
                                            self.resolution, self.close_path)
            self._drawing_path_key = key
        return self._drawing_path_cache

    def get_draw_points(self):
        """Return path-space points; Scene gizmos use get_world_draw_points.

        Baked routes are world-space; local runtime startup converts the public
        path to local coordinates. Reuse arc tables until geometry changes.
        """
        path = self._drawing_path()
        if path is None:
            return []
        key = (tuple(tuple(p) for p in path.points), path.kind, path.closed,
               path.resolution)
        if key != self._draw_key:
            self._draw_points = path.get_draw_points()
            self._draw_key = key
        return self._draw_points

    def get_world_draw_points(self):
        """Project the current draw points to the Scene gizmo coordinate space."""
        target = self._target_object().transform
        local_points = self.local and (
            self._runtime_tween is not None or self._authored_path() is None
        )
        parent = target.parent if local_points else None
        points = self.get_draw_points()
        key = (
            tuple(tuple(p) for p in points),
            tuple(parent.local_to_world_matrix()) if parent is not None else (),
        )
        if key != self._world_draw_key:
            self._world_draw_points = tuple(
                tuple(parent.transform_point(p) if parent is not None else p)
                for p in points
            )
            self._world_draw_key = key
        return self._world_draw_points
