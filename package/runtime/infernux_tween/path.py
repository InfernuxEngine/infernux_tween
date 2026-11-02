"""Arc-length paths sampled without rebuilding control points during playback."""
from bisect import bisect_left
from copy import copy
from enum import Enum
from functools import cached_property
from math import atan2, degrees, isfinite
from typing import Callable, overload

from infernux.components.builtin import Rigidbody
from infernux.lib import Transform, Vector3, quatf
from infernux.lib._Infernux import (
    _MotionPathSnapshot, _MotionPathData, _bezier_closing_handles,
    _tween_float32 as _float32, _motion_path_speed,
    _MotionControlPoint as ControlPoint, _MotionControlPointArray as ControlPointArray,
    _Float32Array as Float32Array, _motion_waypoint_index, _motion_waypoint_fraction,
)

from .core import (
    AxisConstraint,
    _bind_arguments,
    _default_manager,
    _root_control,
    _UNSET,
    LoopType,
    Tween,
    TweenerCore,
    UpdateType,
)
from .array import Vector3Array
from ._builtin_plugins import _Options, _option_field
from .plugin import AbsTweenPlugin, UpdateNotice, _from_arguments
from .ease import EaseManager

_MIN_LOOK_AHEAD = _float32(.0001)
_MAX_LOOK_PERCENTAGE = _float32(1.00001)
_DIRECTION_ZERO_SQUARED = _float32(9.99999944e-11)
_ROTATION_X, _ROTATION_Y, _ROTATION_Z = (int(axis) for axis in (AxisConstraint.X, AxisConstraint.Y, AxisConstraint.Z))


class PathType(Enum):
    LINEAR = 0
    CATMULL_ROM = 1
    CUBIC_BEZIER = 2


class PathMode(Enum):
    FULL3_D = 1
    SIDESCROLLER2_D = 3
    TOP_DOWN2_D = 2
    IGNORE = 0


class OrientType(Enum):
    NONE = 0
    TO_PATH = 1
    LOOK_AT_TRANSFORM = 2
    LOOK_AT_POSITION = 3


class TweenInspectorMode(Enum):
    DEFAULT = 0
    INFO_AND_WAYPOINTS_ONLY = 1
    DEVELOPER = 2
    ONLY_PATH = 3


class HandlesType(Enum):
    FREE = 0
    FULL = 1


class HandlesDrawMode(Enum):
    ORTHOGRAPHIC = 0
    PERSPECTIVE = 1


def _path_field(name, storage, value_type=None):
    field = _option_field(name, storage)
    if value_type is None:
        return field
    def write(self, value):
        field.fset(self, value_type(*value))
    return property(field.fget, write)


class PathOptions(_Options):
    _fields = (
        ('mode', '_mode'), ('orient_type', '_orient_type'),
        ('lock_position_axis', '_lock_position'), ('lock_rotation_axis', '_lock_rotation'),
        ('is_closed_path', '_closed'), ('look_at_position', '_look_position'),
        ('look_at_transform', '_look_transform'), ('look_ahead', '_look_ahead'),
        ('has_custom_forward_direction', '_custom_forward'), ('forward', '_forward_correction'),
        ('use_local_position', '_use_local'), ('parent', '_orientation_parent'),
        ('is_rigidbody', '_body'), ('is_rigidbody2d', '_body2d'),
        ('stable_z_rotation', '_stable_z_rotation'), ('startup_rot', '_startup_rotation'),
        ('startup_z_rot', '_startup_z_rotation'), ('added_extra_start_wp', '_added_extra_start_wp'),
        ('added_extra_end_wp', '_added_extra_end_wp'),
    )
    _defaults = (
        ('mode', PathMode.IGNORE), ('orient_type', OrientType.NONE),
        ('lock_position_axis', AxisConstraint.NONE), ('lock_rotation_axis', AxisConstraint.NONE),
        ('is_closed_path', False), ('look_at_transform', None), ('look_ahead', 0.),
        ('has_custom_forward_direction', False), ('use_local_position', False), ('parent', None),
        ('is_rigidbody', False), ('is_rigidbody2d', False), ('stable_z_rotation', False),
        ('startup_z_rot', 0.), ('added_extra_start_wp', False), ('added_extra_end_wp', False),
    )

    def __init__(self):
        super().__init__()
        self._values.update(look_at_position=Vector3(), forward=quatf(0, 0, 0, 0), startup_rot=quatf(0, 0, 0, 0))

    def __copy__(self):
        result = type(self)()
        result._values = {name: (type(value)(*value) if name in ('look_at_position', 'forward', 'startup_rot') else value)
                          for name, _ in self._fields for value in (getattr(self, name),)}
        return result

    def reset(self):
        super().reset()
        self.look_at_position = Vector3()
        self.forward = self.startup_rot = quatf.identity()


for _field, _storage in PathOptions._fields:
    setattr(PathOptions, _field, _path_field(_field, _storage,
        Vector3 if _field == 'look_at_position' else quatf if _field in ('forward', 'startup_rot') else None))
del _field, _storage


class Path:
    def __init__(self, *args, **kwargs):
        self._reset_incremental_path()
        self._wp_lengths = None
        if 'path_type' in kwargs:
            if 'type' in kwargs:
                raise TypeError("duplicate path type")
            kwargs['type'] = kwargs.pop('path_type')
        if args and isinstance(args[0], PathType) or 'type' in kwargs:
            self.kind, points, self.resolution, self.gizmo_color = _bind_arguments(
                ('type', 'waypoints', 'subdivisions_x_segment', 'gizmo_color'), args, kwargs,
                {'subdivisions_x_segment': 10, 'gizmo_color': None})
            self._points = self._waypoints = Vector3Array(Vector3(*point) for point in points)
            self._control_points = None
            self.closed, self._tables, self.length = False, None, 0.
            self.segments = (len(self.points) - 1) // (3 if self.kind == PathType.CUBIC_BEZIER else 1)
            return
        start, waypoints, kind, resolution, closed = _bind_arguments(
            ('start', 'waypoints', 'kind', 'resolution', 'closed'), args, kwargs,
            {'kind': PathType.LINEAR, 'resolution': 10, 'closed': False})
        if not isinstance(kind, PathType):
            raise TypeError("kind must be PathType")
        if type(resolution) is not int or type(closed) is not bool:
            raise TypeError("resolution must be int and closed must be bool")
        self.kind, self.resolution = kind, resolution
        if not waypoints or self.resolution < 1:
            raise ValueError("A path needs waypoints and resolution >= 1")
        self._points = [Vector3(*start), *(Vector3(*point) for point in waypoints)]
        if self.kind == PathType.CUBIC_BEZIER:
            if len(waypoints) % 3:
                raise ValueError("Bezier groups are endpoint, start handle, end handle")
            if closed and self.points[-3] != self.points[0]:
                end = self.points[-3]
                self.points.extend(
                    (
                        self.points[0],
                        end * 2 - self.points[-1],
                        self.points[0] * 2 - self.points[2],
                    )
                )
            self.segments = (len(self.points) - 1) // 3
        else:
            if closed and self.points[-1] != self.points[0]:
                self.points.append(self.points[0])
            self.segments = len(self.points) - 1
        self.closed = closed
        self._attach_data(_MotionPathData(self.points, self.kind.value, self.resolution, self.closed), initialize_lengths=True)

    def _attach_data(self, data, *, initialize_lengths=False):
        self._tables = data
        self._waypoints = data.points
        self._points = data.recipe_points if self.kind == PathType.CUBIC_BEZIER else self._waypoints
        self._control_points = data.controls
        self.segments, self.length = data.segments, data.length
        if initialize_lengths:
            self._wp_lengths = Float32Array(data.waypoint_lengths)
        self.__dict__.pop('parameters', None)

    @property
    def points(self):
        return self._points

    @points.setter
    def points(self, values):
        if self.kind == PathType.CUBIC_BEZIER and self._tables is not None:
            values = [Vector3(*point) for point in values]
            endpoints = Vector3Array([values[0], *values[1::3]])
            controls = ControlPointArray(ControlPoint(values[index + 1], values[index + 2]) for index in range(1, len(values), 3))
            self._attach_data(self._tables.with_waypoints(endpoints).with_controls(controls))
        else:
            self.wps = values

    @property
    def wps(self):
        return self._waypoints

    @wps.setter
    def wps(self, values):
        values = values if isinstance(values, Vector3Array) else Vector3Array(Vector3(*point) for point in values)
        if self._tables is None:
            self._points = self._waypoints = values
        else:
            self._attach_data(self._tables.with_waypoints(values))

    @property
    def control_points(self):
        return self._control_points

    @control_points.setter
    def control_points(self, values):
        values = values if values is None or isinstance(values, ControlPointArray) else ControlPointArray(values)
        if self._tables is not None:
            self._attach_data(self._tables.with_controls(values))
        self._control_points = values

    @cached_property
    def parameters(self):
        return self._tables.parameters

    @property
    def wp_lengths(self):
        return self._wp_lengths

    @wp_lengths.setter
    def wp_lengths(self, values):
        self._wp_lengths = values if values is None or isinstance(values, Float32Array) else Float32Array(values)

    @cached_property
    def distances(self):
        return self._tables.distances

    @cached_property
    def waypoint_distances(self):
        return self._tables.waypoint_distances

    def compile(self) -> _MotionPathSnapshot:
        """Capture immutable native geometry; large sampling jobs release the GIL.

        Keep this result for repeated sample_many/sample_into calls. Later edits
        to the author's points do not mutate an in-flight computation snapshot.
        """
        return _MotionPathSnapshot([tuple(point) for point in self.points],
                                   self.kind.value, self.resolution, self.closed)

    def _translate(self, offset):
        self._attach_data(self._tables.translated(offset))

    def _reset_incremental_path(self):
        self._incremental_index = 0
        self._incremental_geometry = None

    def _clone_incremental(self, index):
        if index != self._incremental_index:
            if self._incremental_geometry is not None:
                self._incremental_geometry.destroy()
            offset = (self.wps[-1] - self.wps[0]) * index
            data = self._tables.incremental_clone(offset)
            clone = copy(self)
            clone._attach_data(data)
            clone._reset_incremental_path()
            self._incremental_geometry, self._incremental_index = clone, index
        return self._incremental_geometry

    def evaluate(self, parameter):
        return self._tables.evaluate(parameter)

    def point(self, progress):
        if self._tables is None and self.kind == PathType.LINEAR and progress <= 0:
            return Vector3(*self.points[0])
        return self._tables.sample(progress)

    def parameter_at(self, progress):
        return self._tables.parameter_at(progress)

    def get_draw_points(self, subdivisions_x_segment=10):
        if type(subdivisions_x_segment) is not int or subdivisions_x_segment < 1:
            raise ValueError("subdivisions_x_segment must be a positive int")
        if self.kind == PathType.LINEAR:
            return list(self.points)
        steps = (self.segments + 1) * subdivisions_x_segment
        return [self.evaluate(i * self.segments / steps) for i in range(steps + 1)]

    def end_tangent(self):
        if self.kind == PathType.CUBIC_BEZIER:
            return self.points[-3] - self.points[-1]
        return self.points[-1] - self.points[-2]

    def destroy(self):
        self._tables = self._points = self._waypoints = self._control_points = self._wp_lengths = None


class _PathOrientation:
    __slots__ = ('_mode', '_look_at', '_closed', '_lock_rotation', '_startup_rotation', '_stable_z_rotation',
                 '_startup_z_rotation', '_custom_forward', '_forward_correction', '_orientation_parent',
                 '_use_local', '_path_target', '_body', '_compiled_path')

    def __init__(self, values, rewind_step):
        kind = values['_orient_type']
        self._look_at = (values['_look_ahead'] if kind == OrientType.TO_PATH else
                         values['_look_position'].__copy__() if kind == OrientType.LOOK_AT_POSITION else
                         values['_look_transform'] if kind == OrientType.LOOK_AT_TRANSFORM else None)
        self._compiled_path = None
        if kind == OrientType.NONE:
            return
        self._stable_z_rotation = values['_stable_z_rotation']
        self._startup_rotation = quatf(*values['_startup_rotation']) if rewind_step else None
        self._custom_forward = values['_custom_forward']
        self._forward_correction = quatf(*values['_forward_correction']) if self._custom_forward else None
        if kind != OrientType.TO_PATH:
            return
        self._mode, self._closed = values['_mode'], values['_closed']
        self._lock_rotation, self._startup_z_rotation = values['_lock_rotation'], values['_startup_z_rotation']
        self._orientation_parent, self._use_local = values['_orientation_parent'], values['_use_local']

    @classmethod
    def from_options(cls, options, rewind_step):
        owner = options._owner
        values = (owner.__dict__ if owner is not None else
                  {storage: options._values[field] for field, storage in options._fields})
        return cls(values, rewind_step)


def _set_path_orientation(context, tween, path, percentage, position, rewind_step):
    target = tween.target
    context._path_target = target if isinstance(target, (Transform, Rigidbody)) else target.transform
    context._body = isinstance(target, Rigidbody)
    PathTween._set_orientation(context, path, percentage, position, rewind_step)


def _apply_path(tween, path, setter, factor, closed, orientation, inverse, steps, rewind_step, previous=0.):
    if not closed:
        incremental = tween._incremental_cycles(0, False)
        if incremental > 0:
            path = path._clone_incremental(incremental)
    geometry = path._tables
    position = path.point(factor)
    setter(position)
    if orientation is not None:
        percentage = geometry.parameter_at(factor) / path.segments if path.kind != PathType.LINEAR else factor
        if orientation is tween and tween.target is tween._path_target:
            PathTween._set_orientation(orientation, path, percentage, position, rewind_step)
        else:
            _set_path_orientation(orientation, tween, path, percentage, position, rewind_step)
    forward = (not tween._backwards) != inverse
    waypoint = _motion_waypoint_index(path.wp_lengths, path.segments + 1, factor, path.length, forward)
    previous_waypoint = tween._waypoint
    tween._waypoint = waypoint
    if waypoint != previous_waypoint and tween._callbacks.get('waypoint') is not None:
        manager = tween._callback_manager or tween._owner or _default_manager
        if steps is None:
            steps = tween._completed_steps(previous, tween._is_complete_at(previous), tween._backwards) if tween._duration else 0
        backwards = tween.is_looping_or_executing_backwards()
        boundary = (0 if tween._backwards else path.segments
                    if tween.loop_type != LoopType.YOYO or tween.completed_loops() % 2 else 0)
        indices = (range(previous_waypoint + 1, waypoint) if not backwards and waypoint > previous_waypoint else
                   range(previous_waypoint - 1, waypoint, -1) if backwards and waypoint < previous_waypoint else ())
        for index in indices:
            PathTween._call_waypoint(tween._callbacks.get('waypoint'), index, manager)
        if steps and not tween.is_complete() and waypoint != boundary:
            PathTween._call_waypoint(tween._callbacks.get('waypoint'), boundary, manager)
        PathTween._call_waypoint(tween._callbacks.get('waypoint'), waypoint, manager)


class PathTween(TweenerCore):
    def __init__(
        self,
        target,
        waypoints,
        duration,
        kind,
        mode,
        resolution,
        local=False,
        gizmo_color=None,
    ):
        if not isinstance(target, (Transform, Rigidbody)):
            raise TypeError("A path target must be a Transform or Rigidbody")
        if not isinstance(kind, PathType) or not isinstance(mode, PathMode):
            raise TypeError("A path requires PathType and PathMode")
        body, name = isinstance(target, Rigidbody), 'local_position' if local else 'position'
        transform = target.transform if body else target
        getter_target = transform if local else target
        getter = lambda: getattr(getter_target, name)
        if body:
            def setter(value):
                parent = transform.parent if local else None
                target.move_position(parent.transform_point(value) if parent is not None else value)
        else:
            setter = lambda value: setattr(target, name, value)
        self._setup(getter, setter, Path(kind, waypoints, resolution, gizmo_color), duration, mode, local, gizmo_color)
        self.target, self._path_target, self._body = target, target, body
        self._builtin_setter = setter
        if body:
            self.set_update(UpdateType.FIXED)

    def _setup(self, getter, setter, path, duration, mode=PathMode.FULL3_D, local=False, gizmo_color=None):
        super().__init__(getter, setter, path, duration)
        self._delta = None
        self._reset_path_options()
        self.local, self._use_local, self._mode = local, local, mode
        self._name = 'local_position' if local else 'position'
        self._kind, self._resolution = path.kind, path.resolution
        self.gizmo_color = (
            [1.0, 1.0, 1.0, 0.7] if gizmo_color is None else list(gizmo_color)
        )
        self._look_at = None
        self._path = None
        self._compiled_path = None
        self._builtin_setter = None
        self._previous_position = 0.0
        self._path_target = None

    @classmethod
    def _from_plugin(cls, getter, setter, path, duration):
        tween = cls.__new__(cls)
        tween._setup(getter, setter, path, duration, PathMode.IGNORE)
        return tween

    def set_target(self, target):
        super().set_target(target)
        if isinstance(target, (Transform, Rigidbody)):
            self._path_target = target
        return self

    def get_plugin(self):
        return PathPlugin.get()

    def _reset_path_options(self):
        defaults = PathOptions()
        defaults.reset()
        for field, storage in defaults._fields:
            setattr(self, storage, getattr(defaults, field))

    @property
    def start_value(self):
        return self._start

    @start_value.setter
    def start_value(self, value):
        self._start = value

    @property
    def change_value(self):
        return self._delta

    @change_value.setter
    def change_value(self, value):
        self._delta = value

    def _core_options_changed(self):
        self._sync_look_at()

    def _core_option_changed(self, storage):
        if storage in ('_orient_type', '_look_position', '_look_transform', '_look_ahead'):
            self._sync_look_at()

    def _sync_look_at(self):
        self._look_at = (self._look_ahead if self._orient_type == OrientType.TO_PATH else
                         self._look_position if self._orient_type == OrientType.LOOK_AT_POSITION else
                         self._look_transform if self._orient_type == OrientType.LOOK_AT_TRANSFORM else None)

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
    def set_options(
        self,
        lock_position: AxisConstraint,
        lock_rotation: AxisConstraint = AxisConstraint.NONE,
    ): ...

    @overload
    def set_options(
        self,
        close_path: bool,
        lock_position: AxisConstraint = AxisConstraint.NONE,
        lock_rotation: AxisConstraint = AxisConstraint.NONE,
    ): ...

    def set_options(self, *args, **kwargs):
        if not self._active:
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
        return self

    @overload
    def set_look_at(
        self,
        look_ahead: float,
        forward_direction: Vector3 | None = None,
        up: Vector3 | None = None,
    ): ...

    @overload
    def set_look_at(self, look_ahead: float, stable_z_rotation: bool): ...

    @overload
    def set_look_at(
        self,
        look_at_position: Vector3,
        forward_direction: Vector3 | None = None,
        up: Vector3 | None = None,
    ): ...

    @overload
    def set_look_at(self, look_at_position: Vector3, stable_z_rotation: bool): ...

    @overload
    def set_look_at(
        self,
        look_at_transform: Transform,
        forward_direction: Vector3 | None = None,
        up: Vector3 | None = None,
    ): ...

    @overload
    def set_look_at(self, look_at_transform: Transform, stable_z_rotation: bool): ...

    def set_look_at(self, *args, **kwargs):
        if not self._active:
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
            forward_direction, up = _bind_arguments(
                ("forward_direction", "up"),
                tail,
                kwargs,
                {"forward_direction": None, "up": None},
            )
            if any(
                value is not None and not isinstance(value, Vector3)
                for value in (forward_direction, up)
            ):
                raise TypeError("forward_direction and up must be Vector3 or None")
            stable = False
        if isinstance(look_at, (int, float)):
            if not isfinite(look_at):
                raise ValueError("look_ahead must be finite")
            look_at = max(_MIN_LOOK_AHEAD, _float32(look_at))
        self._orient_type = (OrientType.TO_PATH if isinstance(look_at, (int, float)) else
                             OrientType.LOOK_AT_POSITION if isinstance(look_at, Vector3) else OrientType.LOOK_AT_TRANSFORM)
        if self._orient_type == OrientType.TO_PATH:
            self._look_ahead = look_at
        elif self._orient_type == OrientType.LOOK_AT_POSITION:
            self._look_position = Vector3(*look_at)
        else:
            self._look_transform = look_at
        self._sync_look_at()
        self._stable_z_rotation = stable
        custom = (
            forward_direction is not None
            and forward_direction.sqr_magnitude != 0
            or up is not None
            and up.sqr_magnitude != 0
        )
        forward = (
            forward_direction
            if forward_direction is not None and forward_direction.sqr_magnitude != 0
            else Vector3(0, 0, 1)
        )
        self._custom_forward = custom
        self._forward_correction = (
            quatf.look_rotation(forward, Vector3(0, 1, 0) if up is None else up)
            if custom
            else quatf.identity()
        )
        return self

    def on_waypoint_change(self, action: Callable[[int], None]):
        return self._on("waypoint", action)

    def _finalize_end_path(self):
        path = self._end
        self._kind, self._resolution = path.kind, path.resolution
        if path._tables is None:
            origin = self._getter()
            points = [Vector3(*(origin[i] if self._lock_position & (2 << i) else point[i]
                                for i in range(3))) for point in path.points]
            auto_close = self._closed
            if self._kind == PathType.CUBIC_BEZIER:
                auto_close = False
                if self._closed and len(points) >= 3 and (points[-3] - origin).sqr_magnitude >= _DIRECTION_ZERO_SQUARED:
                    handles = _bezier_closing_handles(origin, points[-3], points[1], points[-1])
                    points.extend((Vector3(0, 0, 0), *handles))
            finalized = Path(origin, points, self._kind, self._resolution, auto_close)
            finalized.closed = self._closed
            path.__dict__.update(finalized.__dict__)
        self._delta = path

    def _ensure_initialized(self):
        if not self._initialized:
            if self._compiled_path is not None:
                self._end = self._compiled_path
            if self._from:
                self._relative = False
            else:
                self._start = self.get_plugin().convert_to_start_value(self, self._getter())
            if self._relative:
                self.get_plugin().set_relative_end_value(self)
            self._finalize_end_path()
            self._path = self._end
            self._origin = Vector3(*self._end.points[0])
            transform = self._path_target.transform if self._body else self._path_target
            self._orientation_parent = transform.parent if transform is not None and self._orient_type == OrientType.TO_PATH else None
            self._rotation = transform.euler_angles if transform is not None else Vector3()
            self._startup_rotation = transform.rotation if transform is not None else quatf.identity()
            self._startup_z_rotation = self._rotation.z
            if self._speed_based:
                self._duration = _float32(self._speed_duration(self._duration))
        return Tween._ensure_initialized(self)

    def _speed_duration(self, units):
        return self.get_plugin().get_speed_based_duration(self.plug_options, units, self._delta)

    def _apply_from(self, from_value, set_immediately, relative):
        self._from = True
        return self

    def _change_values(self, *, start=_UNSET, end=_UNSET, duration=-1, snap_start=False):
        if not self._active or self._parent is not None:
            return self
        duration = _float32(duration)
        self._ensure_initialized()
        if start is not _UNSET:
            self._start = start
        if end is not _UNSET:
            self._end, self._relative = end, False
            if snap_start:
                self._start = self.get_plugin().convert_to_start_value(self, self._getter())
        self._finalize_end_path()
        if duration > 0:
            self._duration = _float32(self._speed_duration(duration)) if self._speed_based else duration
            self._update_clock_kind()
        self._seek_serial += 1
        self._seek(min(self._position, self._delay), self._position, False, notify_update=False)
        if self._backwards:
            self.pause()
        return self

    def _on_despawn(self):
        self.get_plugin().reset(self)
        super()._on_despawn()
        self._getter = self._setter = None
        self._builtin_setter = None
        self._reset_path_options()
        self._path = self._compiled_path = self._path_target = None

    def _apply(self, progress, cycle, previous, callbacks):
        path = self._delta
        rewind_step = self._is_rewind_step(self._previous_position)
        self._previous_position = self._position
        closed = self._closed
        inverse = (self.loop_type == LoopType.YOYO and self.has_loops and cycle % 2 == 1) != self._inverted
        orientation = None
        if self._look_at is not None and self._mode != PathMode.IGNORE:
            if self._setter is self._builtin_setter and self._numeric_ease is not None:
                orientation = self
            else:
                orientation = _PathOrientation(self.__dict__, rewind_step)
                orientation._compiled_path = self._compiled_path
        return _apply_path(self, path, self._setter, self._ease(progress), closed, orientation, inverse,
                           None if callbacks else 0, rewind_step, previous)

    @staticmethod
    def _call_waypoint(callback, index, manager):
        if not manager.use_safe_mode:
            callback(index)
            return
        try:
            callback(index)
        except Exception as error:
            manager._record_error(error)

    def _set_orientation(self, path, path_percentage, path_position, rewind_step):
        geometry = path._tables
        transform = self._path_target.transform if self._body else self._path_target
        if self._look_at is None:
            rotation = quatf.identity()
        else:
            world_position = transform.position
            if rewind_step:
                transform.rotation = self._startup_rotation
            up = Vector3(0, 1, 0) if self._stable_z_rotation else transform.up
            if isinstance(self._look_at, (int, float)):
                nonlinear = path.kind != PathType.LINEAR
                if not nonlinear and self._look_at <= _MIN_LOOK_AHEAD:
                    segment = min(path.segments - 1, bisect_left(path.distances, path_percentage * path.length) - 1)
                    segment = max(0, segment)
                    aim = path_position + path.points[segment + 1] - path.points[segment]
                else:
                    look = _float32(path_percentage + self._look_at)
                    look = (_float32(look - 1) if look > 1 and self._closed else
                            min(_MAX_LOOK_PERCENTAGE if nonlinear else 1, look))
                    aim = geometry.evaluate(look * path.segments) if nonlinear else geometry.sample(look)
                if not nonlinear and (aim - path.points[-1]).sqr_magnitude < _DIRECTION_ZERO_SQUARED:
                    aim = (path.points[-1] + path.end_tangent()
                           if (path_position - path.points[-1]).sqr_magnitude < _DIRECTION_ZERO_SQUARED
                           else path.points[-1])
                orientation_parent = self._orientation_parent
                local_parent = orientation_parent if self._use_local else None
                if local_parent is not None:
                    aim = local_parent.transform_point(aim)
                up = transform.up
                if self._lock_rotation:
                    axes = int(self._lock_rotation)
                    if axes & _ROTATION_X:
                        local_aim = transform.inverse_transform_point(aim)
                        local_aim.y = 0
                        aim = transform.transform_point(local_aim)
                        up = local_parent.up if local_parent is not None else Vector3(0, 1, 0)
                    if axes & _ROTATION_Y:
                        local_aim = transform.inverse_transform_point(aim)
                        local_aim.x = 0
                        local_aim.z = abs(local_aim.z)
                        aim = transform.transform_point(local_aim)
                    if axes & _ROTATION_Z:
                        up = (
                            local_parent if local_parent is not None else transform
                        ).transform_direction(Vector3(0, 1, 0))
                        up.z = 0 if self._compiled_path is not None else self._startup_z_rotation
                direction = aim - world_position
                if self._mode == PathMode.FULL3_D and direction.sqr_magnitude < _DIRECTION_ZERO_SQUARED:
                    direction = transform.forward
                if orientation_parent is not None:
                    scale = orientation_parent.local_scale
                    direction = Vector3(*(direction[i] / scale[i] for i in range(3)))
            else:
                aim = (
                    self._look_at.position
                    if isinstance(self._look_at, Transform)
                    else self._look_at
                )
                direction = aim - world_position
            if isinstance(self._look_at, (int, float)) and self._mode != PathMode.FULL3_D:
                if orientation_parent is not None:
                    # The planar angle consumes two scene-space points. Keep
                    # their float stores after scale compensation; taking an
                    # angle directly from the delta changes tiny end probes.
                    direction = (world_position + direction) - world_position
                angle = degrees(atan2(direction.y, direction.x)) % 360
                flipped = self._mode == PathMode.SIDESCROLLER2_D and direction.x < 0
                rotation = quatf.euler(
                    0, 180 if flipped else 0, 180 - angle if flipped else angle
                )
            else:
                rotation = quatf.look_rotation(direction, up)
            if self._custom_forward:
                rotation *= self._forward_correction
        if self._body:
            # The physics path module assigns rotation directly;
            # only its position is a queued MovePosition command.
            self._path_target.rotation = rotation
        else:
            transform.rotation = rotation

    @_root_control
    def goto_waypoint(self, waypoint_index: int, and_play: bool=False) -> None:
        self._ensure_initialized()
        if type(waypoint_index) is not int:
            raise TypeError("waypoint_index must be int")
        path = self._end
        index = min(path.segments, max(0, waypoint_index))
        fraction = _motion_waypoint_fraction(path.wp_lengths, index, path.length)
        cycle, _ = self._progress_at(self._position)
        if self.loop_type == LoopType.YOYO and cycle % 2:
            fraction = 1-fraction
        if self._inverted:
            fraction = 1-fraction
        self._goto(self._delay + _float32((cycle+fraction)*self._duration), and_play, clamp_position=False)

    def _queryable_path(self):
        if self._active and self._parent is None:
            path = self._compiled_path if not self._initialized and self._compiled_path is not None else self._end
            return path if path._tables is not None else None
        return None

    def path_length(self) -> float:
        path = self._queryable_path()
        return path.length if path is not None else -1.0

    def path_get_point(self, path_percentage: float) -> Vector3:
        path = self._queryable_path()
        return path.point(max(0.0,min(1.0,path_percentage))) if path is not None else Vector3(0,0,0)

    def path_get_draw_points(self, subdivisions_x_segment: int=10) -> list[Vector3] | None:
        path = self._queryable_path()
        return path.get_draw_points(subdivisions_x_segment) if path is not None else None


class PathPlugin(AbsTweenPlugin):
    value_type, storage_type, options_type = Vector3, Path, PathOptions
    min_look_ahead = _MIN_LOOK_AHEAD
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self, t):
        t._end.destroy()
        t._start = t._end = t._delta = None

    @overload
    def set_from(self, t, is_relative: bool): ...
    @overload
    def set_from(self, t, from_value, set_immediately: bool, is_relative: bool): ...
    def set_from(self, t, *args, **kwargs):
        if kwargs:
            _from_arguments(args, kwargs)

    def convert_to_start_value(self, t, value):
        return t.end_value

    def set_relative_end_value(self, t):
        path = t.end_value
        if path._tables is None:
            offset = t.getter()
            for index in range(len(path.points)):
                path.points[index] = path.points[index] + offset

    def set_change_value(self, t):
        t._finalize_end_path()

    def get_speed_based_duration(self, options, units_x_second, change_value):
        return _motion_path_speed(change_value.length, units_x_second)

    def evaluate_and_apply(self, options, t, is_relative, getter, setter, elapsed,
                           start_value, change_value, duration, using_inverse_position,
                           new_completed_steps, update_notice):
        rewind_step = update_notice == UpdateNotice.REWIND_STEP
        orientation = (_PathOrientation.from_options(options, rewind_step)
                       if options.orient_type != OrientType.NONE and options.mode != PathMode.IGNORE else None)
        closed = options.is_closed_path
        kernel = t._numeric_ease
        factor = (kernel.evaluate(elapsed, duration) if kernel is not None else
                  EaseManager.evaluate(t, elapsed, duration, t.ease_overshoot_or_amplitude, t.ease_period))
        _apply_path(t, change_value, setter, factor, closed, orientation, using_inverse_position,
                    new_completed_steps, rewind_step)

    def set_orientation(self, options, t, path, path_perc, t_pos, update_notice):
        rewind_step = update_notice == UpdateNotice.REWIND_STEP
        _set_path_orientation(_PathOrientation.from_options(options, rewind_step), t, path, path_perc, t_pos, rewind_step)



def twn_path(target: Transform|Rigidbody, path: list[Vector3], duration: float, path_type: PathType=PathType.LINEAR,
            path_mode: PathMode=PathMode.FULL3_D, resolution: int=10, gizmo_color: list[float]|None=None):
    return _default_manager.add(PathTween(target, path, duration, path_type, path_mode, resolution, gizmo_color=gizmo_color))


def twn_local_path(target: Transform|Rigidbody, path: list[Vector3], duration: float, path_type: PathType=PathType.LINEAR,
                  path_mode: PathMode=PathMode.FULL3_D, resolution: int=10, gizmo_color: list[float]|None=None):
    return _default_manager.add(PathTween(target, path, duration, path_type, path_mode, resolution, local=True, gizmo_color=gizmo_color))
