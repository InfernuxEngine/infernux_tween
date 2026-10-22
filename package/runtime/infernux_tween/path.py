"""Arc-length paths sampled without rebuilding control points during playback."""
from bisect import bisect_right
from enum import Enum
from math import atan2, degrees

from infernux.lib import Transform, Vector3, quatf

from .core import AxisConstraint, DOTween, LoopType, Tween, UpdateType
from .ease import Ease, resolve_ease


class PathType(str, Enum):
    Linear = "Linear"
    CatmullRom = "CatmullRom"
    CubicBezier = "CubicBezier"


class PathMode(str, Enum):
    Full3D = "Full3D"
    Sidescroller2D = "Sidescroller2D"
    TopDown2D = "TopDown2D"
    Ignore = "Ignore"


class Path:
    def __init__(self, start, waypoints, kind=PathType.Linear, resolution=10, closed=False):
        self.kind, self.resolution = PathType(kind), int(resolution)
        if not waypoints or self.resolution < 2:
            raise ValueError("A path needs waypoints and resolution >= 2")
        self.points = [Vector3(*start), *(Vector3(*point) for point in waypoints)]
        if self.kind == PathType.CubicBezier:
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
        self.closed = bool(closed)
        steps = 1 if self.kind == PathType.Linear else self.resolution
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
        if self.kind == PathType.CubicBezier:
            p0 = self.points[0] if segment == 0 else self.points[1 + (segment-1)*3]
            p3, p1, p2 = self.points[1+segment*3:4+segment*3]
            return p0*(1-t)**3 + p1*(3*(1-t)**2*t) + p2*(3*(1-t)*t*t) + p3*t**3
        p1, p2 = self.points[segment:segment+2]
        if self.kind == PathType.Linear:
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


class PathTween(Tween):
    def __init__(self, target, waypoints, duration, kind, mode, resolution, local=False):
        super().__init__(duration)
        from infernux.components.builtin import Rigidbody
        if not isinstance(target, (Transform, Rigidbody)):
            raise TypeError("A path target must be a Transform or Rigidbody")
        self.target, self.local = target, local
        self._name = "local_position" if local else "position"
        self._body = isinstance(target, Rigidbody)
        if self._body:
            if local:
                raise TypeError("Rigidbody paths use world coordinates")
            self.update_type = UpdateType.Fixed
        self._waypoints = [Vector3(*point) for point in waypoints]
        self._kind, self._resolution = PathType(kind), resolution
        self._mode = PathMode(mode)
        self._closed = self._relative = self._speed_based = False
        self._lock_position = self._lock_rotation = AxisConstraint.None_
        self._look_at = None
        self._up = Vector3(0, 1, 0)
        self._path = None
        self._waypoint = -1
        self._ease = resolve_ease(Ease.OutQuad)

    def SetEase(self, ease):
        self._ease = resolve_ease(ease)
        return self

    def _set_relative(self, relative):
        self._relative = relative

    def SetSpeedBased(self, enabled=True):
        self._configure()
        if enabled and self.duration <= 0:
            raise ValueError("Path speed must be positive")
        self._speed_based = bool(enabled)
        return self

    def SetOptions(self, close_path=False, lock_position=AxisConstraint.None_, lock_rotation=AxisConstraint.None_):
        self._configure()
        self._closed = bool(close_path)
        self._lock_position, self._lock_rotation = AxisConstraint(lock_position), AxisConstraint(lock_rotation)
        return self

    def SetLookAt(self, look_at, *, up=(0, 1, 0)):
        self._configure()
        self._look_at, self._up = look_at, Vector3(*up)
        return self

    def OnWaypointChange(self, callback):
        return self._on("waypoint", callback)

    def ForceInit(self):
        if self._path is None:
            self._start = getattr(self.target, self._name)
            points = [point+self._start for point in self._waypoints] if self._relative else self._waypoints
            points = [Vector3(*(self._start[i] if self._lock_position & (1 << i) else point[i] for i in range(3))) for point in points]
            self._path = Path(self._start, points, self._kind, self._resolution, self._closed)
            transform = self.target.transform if self._body else self.target
            self._rotation = transform.local_euler_angles if self.local else transform.euler_angles
            if self._speed_based:
                self.duration = self._path.length / self.duration
        return super().ForceInit()

    def _apply(self, progress, cycle, previous, callbacks):
        self.ForceInit()
        factor = self._ease(progress)
        position = self._path.point(factor)
        if self.loop_type == LoopType.Incremental:
            position += (self._path.point(1)-self._start)*cycle
        if self._body:
            self.target.move_position(position)
        else:
            setattr(self.target, self._name, position)
        if self._look_at is not None and self._mode != PathMode.Ignore:
            transform = self.target.transform if self._body else self.target
            if isinstance(self._look_at, (int, float)):
                look = factor + max(0.00001, self._look_at)
                aim = self._path.point(look % 1 if self._closed else min(1, look))
                direction = aim - position
                if direction.sqr_magnitude < 1e-12:
                    direction = position - self._path.point(max(0, factor-0.00001))
            else:
                aim = self._look_at.position if isinstance(self._look_at, type(transform)) else Vector3(*self._look_at)
                if self.local:
                    aim = transform.parent.inverse_transform_point(aim) if transform.parent is not None else aim
                direction = aim-position
            if direction.sqr_magnitude > 1e-12:
                if self._mode == PathMode.Sidescroller2D:
                    rotation = quatf.euler(0, 0, degrees(atan2(direction.y, direction.x)))
                elif self._mode == PathMode.TopDown2D:
                    rotation = quatf.euler(0, degrees(atan2(direction.x, direction.z)), 0)
                else:
                    rotation = quatf.look_rotation(direction, self._up)
                if self._lock_rotation:
                    angles = rotation.euler_angles
                    rotation = quatf.euler(*(self._rotation[i] if self._lock_rotation & (1 << i) else angles[i] for i in range(3)))
                if self._body:
                    self.target.move_rotation(rotation)
                else:
                    setattr(transform, "local_rotation" if self.local else "rotation", rotation)
        waypoint = bisect_right(self._path.waypoint_distances, min(1, max(0, factor))*self._path.length)
        callback = self._callbacks.get("waypoint")
        if callbacks and callback is not None:
            step = 1 if waypoint >= self._waypoint else -1
            for index in range(self._waypoint+step, waypoint+step, step):
                callback(index)
                if not self.active:
                    break
        self._waypoint = waypoint

    def PathLength(self): return self._path.length if self._path is not None else -1.0
    def PathGetPoint(self, percentage):
        self.ForceInit()
        return self._path.point(percentage)
    def PathGetDrawPoints(self):
        self.ForceInit()
        return [self._path.evaluate(parameter) for parameter in self._path.parameters]


def DOPath(target, waypoints, duration, path_type=PathType.Linear, path_mode=PathMode.Full3D, resolution=10):
    return DOTween.add(PathTween(target, waypoints, duration, path_type, path_mode, resolution))


def DOLocalPath(target, waypoints, duration, path_type=PathType.Linear, path_mode=PathMode.Full3D, resolution=10):
    return DOTween.add(PathTween(target, waypoints, duration, path_type, path_mode, resolution, local=True))
