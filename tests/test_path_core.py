"""Typed path storage, shared native geometry and frozen bulk jobs."""
from array import array
from copy import copy
import gc
import sys
import threading

import pytest
from infernux.lib import SceneManager, Vector3, quatf
from infernux.lib._Infernux import _MotionPathData
import infernux_tween as api


@pytest.fixture
def target():
    scenes = SceneManager.instance()
    scene = scenes.create_scene('Typed path storage')
    owner = scene.create_game_object('Path owner').transform
    yield owner
    api.clear(True)
    scenes.unload_scene(scene)


@pytest.mark.parametrize('original_duration,new_duration', [
    (1e-40, 1.), (1., 1e-40), (1e-40, 1e-41), (.5, 2.),
])
def test_changing_path_duration_matches_a_fresh_path_clock(target, original_duration, new_duration):
    def samples(duration, change):
        target.position = Vector3()
        handle = api.twn_path(target, [Vector3(10, 0, 0)], duration, api.PathType.LINEAR)
        handle.set_ease(api.Ease.LINEAR).set_loops(3).set_auto_kill(False).force_init()
        if change:
            handle.change_end_value(api.Path(api.PathType.LINEAR, [Vector3(10, 0, 0)], 10),
                                    new_duration=new_duration)
        result = []
        for step in (.25, 1., 1.25):
            api.update(step * new_duration)
            result.append((tuple(target.position), handle.elapsed(), handle.completed_loops(), handle.is_complete()))
        api.update(.1 * new_duration)
        result.append((tuple(target.position), handle.elapsed(), handle.completed_loops(), handle.is_complete()))
        handle.kill()
        return result
    assert samples(original_duration, True) == samples(new_duration, False)


def test_waypoint_lengths_expose_shared_float32_buffer_and_pin_its_storage(target):
    handle = api.twn_path(target, [Vector3(2,0,0),Vector3(5,0,0)], 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    path = handle.end_value
    lengths = path.wp_lengths
    assert isinstance(lengths, api.Float32Array) and list(lengths) == [0,2,3]
    view = memoryview(lengths)
    assert view.format == 'f' and view.shape == (3,) and not view.readonly
    view[1] = 1
    assert lengths[1] == 1
    lengths[-1] = 4
    assert view[-1] == 4
    handle.kill()
    assert path.wp_lengths is None and list(view) == [0,1,4]


def test_waypoint_metadata_edits_change_navigation_without_rebuilding_geometry(target):
    handle = api.twn_path(target, [Vector3(2,0,0),Vector3(5,0,0)], 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).pause().force_init()
    path = handle.end_value
    native = path._tables
    handle.goto(.5)
    before = tuple(target.position)
    lengths = api.Float32Array([0,1,4])
    path.wp_lengths = lengths
    assert path.wp_lengths is lengths
    handle.goto(.5)
    assert tuple(target.position) == before and path._tables is native
    handle.goto_waypoint(1)
    assert handle.elapsed() == pytest.approx(.2) and tuple(target.position) == pytest.approx((1,0,0))


def test_waypoint_array_copy_is_independent_and_includes_normal_python_numbers():
    values = api.Float32Array([0,1.1,3])
    separate = copy(values)
    assert list(values) == list(separate)
    separate[1] = 7
    assert values[1] != 7 and separate[1] == 7
    assert type(values[0]) is float
    with pytest.raises(IndexError): values[3] = 1


def test_path_types_are_available_to_star_importing_game_scripts():
    namespace = {}
    exec('from infernux_tween import *', namespace)
    assert namespace['PathOptions']().mode == api.PathMode.IGNORE
    path = namespace['Path'](api.PathType.LINEAR, [Vector3(1,0,0)], 10)
    path.wp_lengths = namespace['Float32Array']([0,1])
    assert list(path.wp_lengths) == [0,1]
    controls = namespace['ControlPointArray']([namespace['ControlPoint'](Vector3(),Vector3(1,0,0))])
    assert tuple(controls[0].b) == (1,0,0) and namespace['PathPlugin'].get() is api.PathPlugin.get()


@pytest.mark.parametrize('kind',['scalar','sequence'])
def test_direct_path_application_keeps_the_callers_clock_and_updates_its_waypoints(target,kind):
    value=[0.]
    caller=(api.to(lambda:value[0],lambda v:value.__setitem__(0,v),1.,1) if kind=='scalar' else
            api.sequence().append_interval(1).append_callback(lambda:None))
    caller.set_target(target).set_ease(api.Ease.LINEAR).set_auto_kill(False).pause().force_init()
    path=api.Path(Vector3(),[Vector3(1,0,0),Vector3(2,0,0)])
    options=api.PathOptions()
    options.reset()
    events=[]
    caller.on_waypoint_change(events.append)
    def getter():
        raise AssertionError('Applying a prepared path must not recapture its start')
    for elapsed in (.75,.25):
        api.PathPlugin.get().evaluate_and_apply(options,caller,False,getter,lambda v:setattr(target,'position',v),
            elapsed,None,path,1,False,0,api.UpdateNotice.NONE)
        assert caller.elapsed()==0 and value[0]==0 and not caller.is_playing()
    assert tuple(target.position)==pytest.approx((.5,0,0)) and events==[0,1,0] and caller._waypoint==0


@pytest.mark.parametrize('waypoint_listener',[False,True])
def test_interval_only_sequence_with_no_timeline_callbacks_remains_uninitialized(waypoint_listener):
    manager=api.TweenManager()
    handle=manager.sequence().append_interval(1).set_auto_kill(False).pause()
    if waypoint_listener:handle.on_waypoint_change(lambda index:None)
    handle.force_init()
    assert handle.is_active() and not handle.is_initialized() and handle.elapsed()==0
    manager.clear(True)


def test_incremental_paths_share_waypoint_metadata_but_keep_their_geometry(target):
    handle = api.twn_path(target, [Vector3(2,0,0),Vector3(2/3,0,0),Vector3(4/3,0,0)], 1, api.PathType.CUBIC_BEZIER)
    handle.set_ease(api.Ease.LINEAR).set_loops(3,api.LoopType.INCREMENTAL).set_auto_kill(False).pause().goto(1.25)
    path = handle.end_value
    clone = path._incremental_geometry
    assert clone.wp_lengths is path.wp_lengths
    path.wp_lengths[1] = 1
    assert clone.wp_lengths[1] == 1
    assert tuple(target.position) == pytest.approx((2.5,0,0),abs=1e-6)
    saved = path.wp_lengths
    path.wp_lengths = [0,5]
    assert path.wp_lengths is not saved and clone.wp_lengths is saved


def test_explicit_path_plugin_uses_shared_storage_and_native_point_edits(target):
    path = api.Path(api.PathType.CATMULL_ROM, [Vector3(1, 2, 3), Vector3(4, 2, 5)], 10)
    handle = api.to(api.PathPlugin.get(), lambda: target.position, lambda value: setattr(target, 'position', value), path, 1)
    handle.set_target(target).set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    assert isinstance(handle, api.TweenerCore) and handle.start_value is handle.end_value is handle.change_value is path
    native, length = path._tables, path.length
    path.points[1].x = 8
    handle.goto(.5)
    assert tuple(target.position) == tuple(native.sample(.5)) and path._tables is native and path.length == length
    fresh = path.compile()
    assert fresh.length != length
    requested = api.Path(api.PathType.LINEAR, [Vector3(10, 0, 0)], 10)
    handle.end_value = requested
    handle.goto(.5)
    assert tuple(target.position) == tuple(native.sample(.5)) and handle.change_value is path
    handle.change_end_value(requested)
    assert handle.start_value is path and handle.change_value is requested
    handle.goto(1)
    assert tuple(target.position) == (10, 0, 0)


def test_path_options_copy_values_detach_old_options_and_release_owner_on_despawn(target):
    handle = api.twn_path(target, [Vector3(2, 0, 0)], 1).set_auto_kill(False)
    old, requested = handle.plug_options, Vector3(1, 2, 3)
    old.look_at_position = requested
    requested.x = 99
    assert tuple(old.look_at_position) == (1, 2, 3)
    separate = copy(old)
    separate.look_at_position.x = 8
    separate.forward.x = .5
    assert tuple(old.look_at_position) == (1, 2, 3) and old.forward.x == 0
    handle.plug_options = separate
    separate.look_at_position.x = old.look_at_position.x = 99
    assert tuple(handle.plug_options.look_at_position) == (8, 2, 3)
    handle.force_init()
    handle.kill()
    assert handle.start_value is handle.end_value is handle.change_value is None
    assert handle.getter is handle.setter is handle._path_target is None
    assert handle.plug_options.mode == api.PathMode.IGNORE
    assert tuple(handle.plug_options.forward) == tuple(handle.plug_options.startup_rot) == tuple(quatf.identity())


def test_path_plugin_direct_evaluation_preserves_the_owners_options(target):
    handle = api.twn_path(target, [Vector3(1, 2, 3), Vector3(4, 2, 5)], 1, api.PathType.CATMULL_ROM)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    options = handle.plug_options
    handle.get_plugin().evaluate_and_apply(options, handle, False, handle.getter, handle.setter, .5,
        handle.start_value, handle.change_value, 1., False, 0, api.UpdateNotice.NONE)
    assert tuple(target.position) == tuple(handle.change_value.point(.5))
    assert handle.plug_options is options and options._owner is handle


def test_shared_incremental_path_reuses_one_clone_until_another_loop_is_requested(target):
    path = api.Path(api.PathType.CUBIC_BEZIER,
                    [Vector3(2,0,0),Vector3(2/3,0,0),Vector3(4/3,0,0)], 10)
    values = [Vector3(), Vector3()]
    handles = [api.to(api.PathPlugin.get(), lambda i=i: values[i],
                     lambda value,i=i: values.__setitem__(i,value),path,1).set_target(target)
               for i in range(2)]
    for handle in handles:
        handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_loops(4,api.LoopType.INCREMENTAL).pause().force_init()
    first, second = handles
    first.goto(1.25)
    assert tuple(values[0]) == pytest.approx((2.5,0,0), abs=1e-6)
    path.wps[-1].x = 4
    second.goto(1.75)
    assert tuple(values[1]) == pytest.approx((3.5,0,0), abs=1e-6)
    second.goto(2.25)
    assert tuple(values[1]) == pytest.approx((8.53125,0,0), abs=1e-6)
    first.kill()
    # Destruction releases the authored geometry; the current translated copy
    # remains usable until another loop requires a new copy of that geometry.
    second.goto(2.75)
    assert tuple(values[1]) == pytest.approx((10.34375,0,0), abs=1e-6)
    second.goto(3.25)
    assert tuple(values[1]) == pytest.approx((10.34375,0,0), abs=1e-6)
    assert path.wps is None


def test_direct_path_evaluation_uses_the_supplied_paths_incremental_cache(target):
    paths = [api.Path(Vector3(start,0,0),
                      [Vector3(start+2,0,0),Vector3(start+2/3,0,0),Vector3(start+4/3,0,0)],
                      api.PathType.CUBIC_BEZIER) for start in (0,10)]
    value = [Vector3()]
    handle = api.to(api.PathPlugin.get(),lambda: value[0],lambda v: value.__setitem__(0,v),paths[0],1).set_target(target)
    handle.set_ease(api.Ease.LINEAR).set_loops(4,api.LoopType.INCREMENTAL).set_auto_kill(False).pause().goto(1.25)
    assert tuple(value[0]) == pytest.approx((2.5,0,0), abs=1e-6)
    def evaluate():
        handle.get_plugin().evaluate_and_apply(handle.plug_options,handle,False,handle.getter,handle.setter,
            .25,handle.start_value,paths[1],1,False,0,api.UpdateNotice.NONE)
    evaluate()
    assert tuple(value[0]) == pytest.approx((12.5,0,0), abs=2e-6)
    paths[1].wps[-1].x = 20
    evaluate()
    assert tuple(value[0]) == pytest.approx((12.5,0,0), abs=2e-6)


@pytest.mark.parametrize('kind',['scalar','sequence','game_object','camera','rigidbody'])
def test_orientation_callback_accepts_any_timeline_without_changing_its_clock(target,kind):
    value=[0.]
    handle=(api.sequence().append_interval(1) if kind=='sequence' else
            api.to(lambda:value[0],lambda v:value.__setitem__(0,v),1.,1))
    receiver=target.game_object if kind=='game_object' else target
    if kind in ('camera','rigidbody'):
        from infernux.components.builtin import Camera, Rigidbody
        receiver=target.game_object.add_component(Camera if kind=='camera' else Rigidbody)
    handle.set_target(receiver).pause().force_init()
    options=api.PathOptions()
    options.mode=api.PathMode.FULL3_D
    options.orient_type=api.OrientType.LOOK_AT_POSITION
    options.look_at_position=Vector3(10,0,0)
    path=api.Path(Vector3(),[Vector3(0,0,1)],api.PathType.LINEAR)
    assert api.PathPlugin.get().set_orientation(options=options, t=handle, path=path,
        path_perc=.5, t_pos=Vector3(), update_notice=api.UpdateNotice.NONE) is None
    assert tuple(target.position)==(0,0,0) and handle.elapsed()==0 and value[0]==0
    assert quatf.angle(target.rotation,quatf.look_rotation(Vector3(1,0,0)))<.001
    assert tuple(options.look_at_position)==(10,0,0)


def test_native_path_point_views_pin_the_geometry_after_the_owner_is_released():
    data = _MotionPathData([Vector3(0,0,0), Vector3(1,2,3), Vector3(4,2,5)], 1, 10, False)
    view = data.points
    pinned = view[1]
    view[1] = Vector3(5, 6, 7)
    assert tuple(pinned) == (5, 6, 7)
    del data, view
    gc.collect()
    pinned.x = 9
    assert tuple(pinned) == (9, 6, 7)


@pytest.mark.parametrize('kind', [0, 1, 2])
def test_mutable_path_bulk_sampling_freezes_geometry_before_releasing_the_gil(kind):
    points = [Vector3(0,0,0), Vector3(1,2,3), Vector3(4,2,5)]
    if kind == 2: points.append(Vector3(3,4,6))
    data = _MotionPathData(points, kind, 10, False)
    expected = array('f', tuple(data.sample(.5)))
    times, output = array('d', [.5]) * 250000, array('f', [0]) * 750000
    armed, edited = threading.Event(), threading.Event()
    def edit():
        armed.wait()
        data.points[1].x = 50
        edited.set()
    thread, previous = threading.Thread(target=edit), sys.getswitchinterval()
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
