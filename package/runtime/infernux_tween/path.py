"""Arc-length paths sampled without rebuilding control points during playback."""
from bisect import bisect_left, bisect_right
from enum import Enum
from math import atan2, degrees, isfinite
from typing import Callable, overload

from infernux.components.builtin import Rigidbody
from infernux.lib import Transform, Vector3, quatf

from .core import AxisConstraint, _bind_arguments, _default_manager, LoopType, Tween, UpdateType


class PathType(Enum):
    LINEAR = "Linear"
    CATMULL_ROM = "CatmullRom"
    CUBIC_BEZIER = "CubicBezier"


class PathMode(Enum):
    FULL3_D = "Full3D"
    SIDESCROLLER2_D = "Sidescroller2D"
    TOP_DOWN2_D = "TopDown2D"
    IGNORE = "Ignore"


class Path:
    def __init__(self, start, waypoints, kind=PathType.LINEAR, resolution=10, closed=False):
        if not isinstance(kind, PathType):
            raise TypeError("kind must be PathType")
        if type(resolution) is not int or type(closed) is not bool:
            raise TypeError("resolution must be int and closed must be bool")
        self.kind, self.resolution = kind, resolution
        if not waypoints or self.resolution < 1:
            raise ValueError("A path needs waypoints and resolution >= 1")
        self.points = [Vector3(*start), *(Vector3(*point) for point in waypoints)]
        if self.kind == PathType.CUBIC_BEZIER:
            if len(waypoints) % 3:
                raise ValueError("Bezier groups are endpoint, start handle, end handle")
            if closed and self.points[-3] != self.points[0]:
                end = self.points[-3]
                self.points.extend((self.points[0], end*2-self.points[-1], self.points[0]*2-self.points[2]))
            self.segments = (len(self.points)-1) // 3
        else:
            if closed and self.points[-1] != self.points[0]:
                self.points.append(self.points[0])
            self.segments = len(self.points) - 1
        self.closed = closed
        steps = 1 if self.kind == PathType.LINEAR else self.resolution
        self.parameters = [i / steps for i in range(self.segments * steps + 1)]
        samples = [self.evaluate(parameter) for parameter in self.parameters]
        self.distances, self.waypoint_distances = [0.0], []
        for index, (a, b) in enumerate(zip(samples, samples[1:]), 1):
            self.distances.append(self.distances[-1] + (b-a).magnitude)
            if index % steps == 0:
                self.waypoint_distances.append(self.distances[-1])
        self.length = self.distances[-1]

    def evaluate(self, parameter):
        segment = min(self.segments - 1, int(parameter))
        t = min(1.0, max(0.0, parameter - segment))
        if self.kind == PathType.CUBIC_BEZIER:
            p0 = self.points[0] if segment == 0 else self.points[1 + (segment-1)*3]
            p3, p1, p2 = self.points[1+segment*3:4+segment*3]
            return p0*(1-t)**3 + p1*(3*(1-t)**2*t) + p2*(3*(1-t)*t*t) + p3*t**3
        p1, p2 = self.points[segment:segment+2]
        if self.kind == PathType.LINEAR:
            return p1 + (p2-p1)*t
        p0 = self.points[segment-1] if segment > 0 else (self.points[-2] if self.closed else p1*2-p2)
        p3 = self.points[segment+2] if segment+2 < len(self.points) else (self.points[1] if self.closed else p2*2-p1)
        return (p1*2 + (p2-p0)*t + (p0*2-p1*5+p2*4-p3)*t*t + (p1*3-p0-p2*3+p3)*t**3)*0.5

    def point(self, progress):
        distance = min(1.0, max(0.0, progress)) * self.length
        index = min(len(self.distances)-2, max(0, bisect_right(self.distances, distance)-1))
        span = self.distances[index+1] - self.distances[index]
        fraction = (distance-self.distances[index])/span if span else 0.0
        return self.evaluate(self.parameters[index] + (self.parameters[index+1]-self.parameters[index])*fraction)

    def end_tangent(self):
        if self.kind == PathType.CUBIC_BEZIER:
            return self.points[-3] - self.points[-1]
        return self.points[-1] - self.points[-2]


class PathTween(Tween):
    def __init__(self, target, waypoints, duration, kind, mode, resolution, local=False, gizmo_color=None):
        super().__init__(duration)
        if not isinstance(target, (Transform, Rigidbody)):
            raise TypeError("A path target must be a Transform or Rigidbody")
        self.target = self._path_target = target
        self.local = local
        self._name = "local_position" if local else "position"
        self._body = isinstance(target, Rigidbody)
        if self._body:
            self.set_update(UpdateType.FIXED)
        self._waypoints = [Vector3(*point) for point in waypoints]
        if not isinstance(kind, PathType) or not isinstance(mode, PathMode):
            raise TypeError("A path requires PathType and PathMode")
        self._kind, self._resolution, self._mode = kind, resolution, mode
        self.gizmo_color = [1.0, 1.0, 1.0, 0.7] if gizmo_color is None else list(gizmo_color)
        self._closed = self._relative = self._speed_based = False
        self._lock_position = self._lock_rotation = AxisConstraint.NONE
        self._look_at = None
        self._forward_correction = quatf.identity()
        self._stable_z_rotation = False
        self._path = None
        self._waypoint = -1

    def _set_relative(self, relative):
        self._relative = relative

    def set_speed_based(self, is_speed_based: bool=True):
        if not self._configure():
            return self
        if is_speed_based and self._duration <= 0:
            raise ValueError("Path speed must be positive")
        self._speed_based = is_speed_based
        return self

    @overload
    def set_options(self, lock_position: AxisConstraint, lock_rotation: AxisConstraint=AxisConstraint.NONE): ...
    @overload
    def set_options(self, close_path: bool, lock_position: AxisConstraint=AxisConstraint.NONE,
                     lock_rotation: AxisConstraint=AxisConstraint.NONE): ...
    def set_options(self, *args, **kwargs):
        if not self._configure():
            return self
        axes_only = args and isinstance(args[0], AxisConstraint) or not args and "close_path" not in kwargs
        if axes_only:
            position, rotation = _bind_arguments(("lock_position", "lock_rotation"), args, kwargs,
                                                {"lock_rotation": AxisConstraint.NONE})
            closed = False
        else:
            closed, position, rotation = _bind_arguments(("close_path", "lock_position", "lock_rotation"), args, kwargs,
                                                        {"lock_position": AxisConstraint.NONE, "lock_rotation": AxisConstraint.NONE})
        if type(closed) is not bool or not isinstance(position, AxisConstraint) or not isinstance(rotation, AxisConstraint):
            raise TypeError("path options require bool and AxisConstraint")
        self._closed, self._lock_position, self._lock_rotation = closed, position, rotation
        self._path = None
        return self

    @overload
    def set_look_at(self, look_ahead: float, forward_direction: Vector3|None=None, up: Vector3|None=None): ...
    @overload
    def set_look_at(self, look_ahead: float, stable_z_rotation: bool): ...
    @overload
    def set_look_at(self, look_at_position: Vector3, forward_direction: Vector3|None=None, up: Vector3|None=None): ...
    @overload
    def set_look_at(self, look_at_position: Vector3, stable_z_rotation: bool): ...
    @overload
    def set_look_at(self, look_at_transform: Transform, forward_direction: Vector3|None=None, up: Vector3|None=None): ...
    @overload
    def set_look_at(self, look_at_transform: Transform, stable_z_rotation: bool): ...
    def set_look_at(self, *args, **kwargs):
        if not self._configure():
            return self
        targets = {"look_ahead": (int, float), "look_at_position": Vector3, "look_at_transform": Transform}
        named = targets.keys() & kwargs.keys()
        if args:
            if named:
                raise TypeError("duplicate look-at target")
            look_at, tail = args[0], args[1:]
        elif len(named) == 1:
            name, = named
            look_at, tail = kwargs.pop(name), ()
            if not isinstance(look_at, targets[name]):
                raise TypeError(f"{name} has an invalid type")
        else:
            raise TypeError("provide one look_ahead, look_at_position or look_at_transform")
        if type(look_at) is bool or not isinstance(look_at, (Transform, Vector3, int, float)):
            raise TypeError("look-at target must be float, Vector3 or Transform")
        if "stable_z_rotation" in kwargs or tail and type(tail[0]) is bool:
            stable, = _bind_arguments(("stable_z_rotation",), tail, kwargs)
            if type(stable) is not bool:
                raise TypeError("stable_z_rotation must be bool")
            forward_direction = up = None
        else:
            forward_direction, up = _bind_arguments(("forward_direction", "up"), tail, kwargs,
                                                    {"forward_direction": None, "up": None})
            if any(value is not None and not isinstance(value, Vector3) for value in (forward_direction, up)):
                raise TypeError("forward_direction and up must be Vector3 or None")
            stable = False
        if isinstance(look_at, (int, float)):
            if not isfinite(look_at):
                raise ValueError("look_ahead must be finite")
            look_at = max(0.0001, float(look_at))
        self._look_at = look_at
        self._stable_z_rotation = stable
        custom = (forward_direction is not None and forward_direction.sqr_magnitude != 0 or
                  up is not None and up.sqr_magnitude != 0)
        forward = forward_direction if forward_direction is not None and forward_direction.sqr_magnitude != 0 else Vector3(0, 0, 1)
        self._forward_correction = (quatf.look_rotation(forward, Vector3(0, 1, 0) if up is None else up)
                                    if custom else quatf.identity())
        return self

    def on_waypoint_change(self, action: Callable[[int], None]):
        return self._on("waypoint", action)

    def force_init(self):
        if self._path is None:
            transform = self._path_target.transform if self._body else self._path_target
            self._start = getattr(transform if self.local else self._path_target, self._name)
            points = [point+self._start for point in self._waypoints] if self._relative else self._waypoints
            points = [Vector3(*(self._start[i] if self._lock_position & (2 << i) else point[i] for i in range(3))) for point in points]
            self._path = Path(self._start, points, self._kind, self._resolution, self._closed)
            self._rotation = transform.euler_angles
            if self._speed_based and not self._initialized:
                self._duration = self._path.length / self._duration
        return super().force_init()

    def _apply(self, progress, cycle, previous, callbacks):
        self.force_init()
        factor = self._ease(progress)
        path_position = self._path.point(factor)
        increment = (self._path.point(1)-self._start)*self._incremental_cycles(cycle)
        position = path_position + increment
        transform = self._path_target.transform if self._body else self._path_target
        parent = transform.parent if self.local else None
        world_position = parent.transform_point(position) if parent is not None else position
        if self._body:
            self._path_target.move_position(world_position)
        else:
            setattr(self._path_target, self._name, position)
        if self._look_at is not None and self._mode != PathMode.IGNORE:
            if isinstance(self._look_at, (int, float)):
                look = factor + self._look_at
                aim = self._path.point(look % 1 if self._closed else min(1, look))
                direction = aim - path_position
                if not self._closed and factor >= 1:
                    direction = self._path.end_tangent()
                if parent is not None:
                    direction = parent.transform_vector(direction)
            else:
                aim = self._look_at.position if isinstance(self._look_at, Transform) else self._look_at
                direction = aim-world_position
            if direction.sqr_magnitude != 0:
                if isinstance(self._look_at, (int, float)) and self._mode in (PathMode.SIDESCROLLER2_D, PathMode.TOP_DOWN2_D):
                    angle = degrees(atan2(direction.y, direction.x)) % 360
                    flipped = self._mode == PathMode.SIDESCROLLER2_D and direction.x < 0
                    rotation = quatf.euler(0, 180 if flipped else 0, 180-angle if flipped else angle)
                else:
                    up = Vector3(0, 1, 0) if self._stable_z_rotation else transform.up
                    rotation = quatf.look_rotation(direction, up)
                rotation *= self._forward_correction
                if self._lock_rotation:
                    angles = rotation.euler_angles
                    rotation = quatf.euler(*(self._rotation[i] if self._lock_rotation & (2 << i) else angles[i] for i in range(3)))
                if self._body:
                    self._path_target.move_rotation(rotation)
                else:
                    transform.rotation = rotation
        distance = min(1, max(0, factor))*self._path.length
        forward = (self.position >= previous) != (self.loop_type == LoopType.YOYO and cycle % 2 == 1)
        if self._inverted:
            forward = not forward
        waypoint = (0 if factor <= 0 else self._path.segments if factor >= 1 else
                    bisect_right(self._path.waypoint_distances, distance) if forward else
                    bisect_left(self._path.waypoint_distances, distance) + 1)
        callback = self._callbacks.get("waypoint")
        if callbacks and callback is not None:
            step = 1 if waypoint >= self._waypoint else -1
            for index in range(self._waypoint+step, waypoint+step, step):
                self._waypoint = index
                if not self._invoke(lambda: callback(index), self.position):
                    return False
        self._waypoint = waypoint

    def goto_waypoint(self, waypoint_index: int, and_play: bool=False):
        self.force_init()
        if type(waypoint_index) is not int:
            raise TypeError("waypoint_index must be int")
        index = min(self._path.segments, max(0, waypoint_index))
        distance = self._path.waypoint_distances[index-1] if index else 0.0
        fraction = distance / self._path.length if self._path.length else 0.0
        cycle, _ = self._progress_at(self.position)
        if self.loop_type == LoopType.YOYO and cycle % 2:
            fraction = 1-fraction
        if self._inverted:
            fraction = 1-fraction
        return self.goto((cycle+fraction)*self._duration, and_play)

    def path_length(self) -> float: return self._path.length if self._path is not None else -1.0
    def path_get_point(self, path_percentage: float) -> Vector3:
        self.force_init()
        return self._path.point(path_percentage)
    def path_get_draw_points(self, subdivisions_x_segment: int=10) -> list[Vector3]:
        self.force_init()
        if type(subdivisions_x_segment) is not int or subdivisions_x_segment < 1:
            raise ValueError("subdivisions_x_segment must be a positive int")
        if self._kind == PathType.LINEAR:
            return list(self._path.points)
        steps = self._path.segments*subdivisions_x_segment
        return [self._path.evaluate(i/subdivisions_x_segment) for i in range(steps+1)]


def do_path(target: Transform|Rigidbody, path: list[Vector3], duration: float, path_type: PathType=PathType.LINEAR,
            path_mode: PathMode=PathMode.FULL3_D, resolution: int=10, gizmo_color: list[float]|None=None):
    return _default_manager.add(PathTween(target, path, duration, path_type, path_mode, resolution, gizmo_color=gizmo_color))


def do_local_path(target: Transform|Rigidbody, path: list[Vector3], duration: float, path_type: PathType=PathType.LINEAR,
                  path_mode: PathMode=PathMode.FULL3_D, resolution: int=10, gizmo_color: list[float]|None=None):
    return _default_manager.add(PathTween(target, path, duration, path_type, path_mode, resolution, local=True, gizmo_color=gizmo_color))
