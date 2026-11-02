"""Native endpoint/control ownership and frozen sampling preserve edits."""
from array import array
from copy import copy
import gc
import sys
import threading

import pytest
from infernux.lib import Vector3
from infernux.lib._Infernux import _MotionPathData
from infernux_tween import Path, PathType, Vector3Array, ControlPoint, ControlPointArray


def curve():
    return Path((0,0,0), [(2,3,4),(1,0,0),(1,2,3),(5,4,3),(3,3,4),(4,4,4)], PathType.CUBIC_BEZIER)


def test_bezier_recipe_endpoints_and_controls_are_views_of_the_same_geometry():
    path = curve()
    assert len(path.points) == 7 and len(path.wps) == 3 and len(path.control_points) == 2
    data = path._tables
    path.wps[1].x = 20
    assert path.points[1].x == 20
    path.points[2].x = 10
    assert path.control_points[0].a.x == 10
    path.control_points[0].b = Vector3(8,9,10)
    assert tuple(path.points[3]) == (8,9,10) and path._tables is data
    frozen = path.compile()
    expected = tuple(frozen.sample(.5))
    path.control_points[0].a.x = 80
    assert tuple(frozen.sample(.5)) == expected and tuple(path.point(.5)) != expected


def test_replacing_waypoints_preserves_tables_controls_and_native_array_references():
    path = curve()
    old_points, old_controls, length = path.wps, path.control_points, path.length
    requested = Vector3Array([Vector3(10,0,0),Vector3(20,0,0),Vector3(30,0,0)])
    path.wps = requested
    assert path.length == length
    requested[1].y = 15
    assert path.wps[1].y == 15
    old_points[1].y = 99
    assert path.wps[1].y == 15
    old_controls[0].a.x = 30
    assert path.control_points[0].a.x == 30
    controls = ControlPointArray([ControlPoint(Vector3(1,2,3),Vector3(4,5,6)) for _ in range(2)])
    path.control_points = controls
    controls[0].a.x = 40
    assert path.control_points[0].a.x == 40
    old_controls[0].a.x = 99
    assert path.control_points[0].a.x == 40 and path.wps[1].y == 15


def test_control_point_copies_and_component_views_keep_value_and_owner_semantics():
    supplied = Vector3(1,2,3)
    point = ControlPoint(supplied, Vector3(4,5,6))
    supplied.x = 99
    assert point.a.x == 1
    detached = copy(point)
    detached.a.x = 8
    assert point.a.x == 1
    values = ControlPointArray([point])
    point.a.x = 10
    assert values[0].a.x == 1
    separate = copy(values)
    separate[0].a.x = 20
    assert values[0].a.x == 1
    pinned = values[0].a
    del values
    gc.collect()
    pinned.y = 40
    assert tuple(pinned) == (1,40,3)


def test_null_and_empty_control_arrays_are_distinct_and_are_not_repaired_during_sampling():
    path = curve()
    length = path.length
    path.control_points = None
    assert path.control_points is None and path.length == length
    with pytest.raises(AttributeError, match='control array is null'):
        path.point(.5)
    path.control_points = []
    assert len(path.control_points) == 0 and path.length == length
    with pytest.raises(IndexError): path.point(.5)


def test_generic_translation_and_incremental_cloning_keep_distinct_control_requirements():
    data = _MotionPathData([Vector3(0,0,0),Vector3(2,0,0)],0,10,False)
    assert data.controls is None
    assert tuple(data.translated(Vector3(3,0,0)).sample(.5)) == (4,0,0)
    with pytest.raises(AttributeError): data.incremental_clone(Vector3(3,0,0))
    configured = data.with_controls(ControlPointArray([]))
    assert tuple(configured.incremental_clone(Vector3(3,0,0)).sample(.5)) == (4,0,0)


@pytest.mark.parametrize('kind', [1,2])
def test_native_translation_keeps_tables_and_owns_independent_endpoint_and_control_arrays(kind):
    points = [Vector3(0,0,0),Vector3(2,3,4),Vector3(5,4,3)]
    if kind == 2: points.append(Vector3(4,4,4))
    data = _MotionPathData(points, kind, 10, False)
    shifted = data.translated(Vector3(10,20,30))
    assert shifted.length == data.length and shifted.distances == data.distances
    assert tuple(shifted.points[0]) == (10,20,30)
    expected = tuple(a+b for a,b in zip(data.controls[0].a, (10,20,30)))
    assert tuple(shifted.controls[0].a) == expected
    data.points[0].x = data.controls[0].a.x = 99
    assert shifted.points[0].x == 10 and tuple(shifted.controls[0].a) == expected


@pytest.mark.parametrize('kind', [0,1,2])
def test_replacing_endpoint_arrays_does_not_invalidate_existing_views(kind):
    points = [Vector3(0,0,0),Vector3(2,3,4),Vector3(5,4,3)]
    if kind == 2: points += [Vector3(4,4,4)]
    data = _MotionPathData(points, kind, 10, False)
    old_view, pinned = data.points, data.points[1]
    new_view = Vector3Array([Vector3(10,0,0),Vector3(20,0,0)])
    replacement = data.with_waypoints(new_view)
    new_view[0].x = 30
    assert replacement.points[0].x == 30
    del data, old_view
    gc.collect()
    pinned.x = 99
    assert replacement.points[0].x == 30 and replacement.points[1].x == 20


@pytest.mark.parametrize('kind', [1,2])
def test_bulk_sampling_freezes_both_endpoint_and_control_arrays(kind):
    points = [Vector3(0,0,0),Vector3(2,3,4),Vector3(5,4,3)]
    if kind == 2: points += [Vector3(4,4,4)]
    data = _MotionPathData(points, kind, 10, False)
    expected = array('f', tuple(data.sample(.5)))
    times, output = array('d', [.5]) * 250000, array('f', [0]) * 750000
    armed, edited = threading.Event(), threading.Event()
    def edit():
        armed.wait()
        data.points[1].x = 80
        data.controls[0].a.x = 50
        edited.set()
    previous, thread = sys.getswitchinterval(), threading.Thread(target=edit)
    try:
        sys.setswitchinterval(10)
        thread.start()
        armed.set()
        data.sample_into(times, output)
        assert edited.is_set() and all(output[i:i+3] == expected for i in range(0, len(output), 3))
        assert tuple(data.sample(.5)) != tuple(expected)
    finally:
        armed.set()
        sys.setswitchinterval(previous)
        thread.join(timeout=5)


def test_control_point_translation_copies_both_handles_with_float32_arithmetic():
    source = ControlPoint(Vector3(16777216, 2, 3), Vector3(-16777216, 5, 6))
    offset = Vector3(1, -2, .5)
    result = source + offset
    assert tuple(result.a) == (16777216, 0, 3.5)
    assert tuple(result.b) == (-16777215, 3, 6.5)
    source.a.y, offset.z = 99, 99
    assert tuple(result.a) == (16777216, 0, 3.5)
    result.b.x = 10
    assert source.b.x == -16777216


def test_control_array_augmented_translation_writes_only_its_selected_pair():
    original = ControlPoint(Vector3(1, 2, 3), Vector3(4, 5, 6))
    values = ControlPointArray([original, original])
    detached = values[0] + Vector3(10, 20, 30)
    detached.a.x = 100
    assert values[0].a.x == 1
    values[0] += Vector3(10, 20, 30)
    assert tuple(values[0].a) == (11, 22, 33)
    assert tuple(values[0].b) == (14, 25, 36)
    assert tuple(values[1].a) == (1, 2, 3)
    assert tuple(original.b) == (4, 5, 6)


def test_control_point_text_displays_both_handles_with_fixed_decimal_places():
    value = ControlPoint(Vector3(1.126, -2.5, 0), Vector3(4, 5.126, 6))
    assert str(value) == '[(1.13, -2.50, 0.00) | (4.00, 5.13, 6.00)]'
