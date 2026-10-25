from infernux.components import FieldType, add_component_menu, serialized_field
from infernux.components.builtin import Rigidbody
from infernux.lib import Vector3

from infernux_tween import Path, PathMode, PathType, shortcuts as S
from .TweenAuthoring import TweenAuthoring


@add_component_menu("Animation/Tween Path")
class TweenPath(TweenAuthoring):
    _draw_key = None
    _draw_points = ()
    waypoints: list = serialized_field(default=[(0.0, 1.0, 0.0)], field_type=FieldType.LIST,
                                      element_type=FieldType.VEC3, display_name_key="tween.waypoints")
    path_type: PathType = serialized_field(default=PathType.CATMULL_ROM, display_name_key="tween.path_type",
                                          enum_labels=["tween.path_type."+e.name for e in PathType])
    path_mode: PathMode = serialized_field(default=PathMode.FULL3_D, display_name_key="tween.path_mode",
                                          enum_labels=["tween.path_mode."+e.name for e in PathMode])
    resolution: int = serialized_field(default=10, range=(2, 100), slider=False, display_name_key="tween.resolution")
    local: bool = serialized_field(default=False, display_name_key="tween.local")
    close_path: bool = serialized_field(default=False, display_name_key="tween.close_path")
    use_rigidbody: bool = serialized_field(default=False, display_name_key="tween.use_rigidbody")
    orient_to_path: bool = serialized_field(default=False, display_name_key="tween.orient_to_path")
    look_ahead: float = serialized_field(default=0.01, range=(0.001, 1), display_name_key="tween.look_ahead",
                                        visible_when=lambda c: c.orient_to_path)

    def _build(self, preview=False):
        obj = self._target_object()
        target = obj.transform
        if self.use_rigidbody and not preview:
            target = obj.get_component(Rigidbody)
            if target is None:
                raise ValueError(f"{obj.name} needs a Rigidbody")
        shortcut = S.do_local_path if self.local else S.do_path
        tween = shortcut(target, self.waypoints, self.duration, self.path_type, self.path_mode, self.resolution)
        tween.set_options(self.close_path)
        if self.orient_to_path:
            tween.set_look_at(self.look_ahead)
        return tween

    def _capture_preview(self, scope):
        target = self._target_object().transform
        scope.capture(target, "local_position" if self.local else "position", "local_rotation" if self.local else "rotation")

    def world_waypoint(self, index):
        target = self._target_object().transform
        point = Vector3(*self.waypoints[index])
        if self.relative:
            point += target.local_position if self.local else target.position
        if self.local and target.parent is not None:
            point = target.parent.transform_point(point)
        return point

    def _restart_from_here(self):
        tween = self.tween
        tween.force_init()
        target = tween._path_target.transform if tween.local and tween._body else tween._path_target
        offset = getattr(target, tween._name) - tween._start
        tween._path.points = [point + offset for point in tween._path.points]
        tween._start += offset

    def waypoint_from_world(self, point):
        target = self._target_object().transform
        point = Vector3(*point)
        if self.local and target.parent is not None:
            point = target.parent.inverse_transform_point(point)
        if self.relative:
            point -= target.local_position if self.local else target.position
        return tuple(point)

    def draw_points(self):
        target = self._target_object().transform
        parent = target.parent if self.local else None
        start = target.local_position if self.local else target.position
        key = (tuple(start), tuple(tuple(p) for p in self.waypoints), self.path_type, self.resolution,
               self.close_path, self.relative, tuple(parent.local_to_world_matrix()) if parent is not None else ())
        if key != self._draw_key:
            points = [Vector3(*p) + start if self.relative else Vector3(*p) for p in self.waypoints]
            if points:
                path = Path(start, points, self.path_type, self.resolution, self.close_path)
                samples = [path.evaluate(p) for p in path.parameters]
                self._draw_points = tuple(tuple(parent.transform_point(p) if parent is not None else p) for p in samples)
            else:
                self._draw_points = ()
            self._draw_key = key
        return self._draw_points
