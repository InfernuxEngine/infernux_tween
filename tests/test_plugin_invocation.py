"""Value fields and explicit plugin arguments retain their call boundaries."""
from copy import copy
from math import cos, sin, pi, sqrt

import pytest
from infernux.lib import Vector2, quatf
import infernux_tween as api
from infernux_tween.rotation import QuaternionTweener


def make_handle(manager,kind,getter,setter):
    if kind == 'quaternion':
        return manager.add(QuaternionTweener(getter,setter,quatf(.2,.4,.6,.8),1))
    return manager.to(api.CirclePlugin.get(),getter,setter,Vector2(.2,.4),1).set_options(120,False,False)


@pytest.mark.parametrize('kind',['quaternion','circle'])
@pytest.mark.parametrize('field',['start_value','end_value','change_value'])
def test_assigning_value_fields_copies_inputs_and_retains_live_component_edits(kind,field):
    manager = api.TweenManager()
    current = quatf(.1,.2,.3,.9) if kind == 'quaternion' else Vector2(.1,.2)
    supplied = quatf(.4,.5,.6,.7) if kind == 'quaternion' else Vector2(.4,.5)
    handle = make_handle(manager,kind,lambda:current,lambda value:None).set_auto_kill(False)
    handle.force_init()
    setattr(handle,field,supplied)
    supplied.x = 99
    assert getattr(handle,field).x == pytest.approx(.4)
    getattr(handle,field).x = .8
    assert getattr(handle,field).x == pytest.approx(.8)
    manager.clear()


def test_quaternion_implicit_from_saves_the_old_endpoint_before_the_getter():
    manager = api.TweenManager()
    def getter():
        handle.end_value.x = 9
        return quatf(.1,.2,.3,.9)
    handle = make_handle(manager,'quaternion',getter,lambda value:None).set_auto_kill(False)
    handle.from_()
    assert tuple(handle.start_value) == pytest.approx((.2,.4,.6,.8),abs=1e-7,rel=0)
    assert tuple(handle.end_value) == pytest.approx((.1,.2,.3,.9),abs=1e-7,rel=0)
    manager.clear()


@pytest.mark.parametrize('change_angle,snapping,expected',[(180,False,(1,0)),(90,True,(1,1))])
def test_circle_plugin_uses_the_passed_change_and_options(change_angle,snapping,expected):
    manager,values = api.TweenManager(),[]
    handle = manager.to(api.CirclePlugin.get(),lambda:Vector2(0,1),values.append,Vector2(0,0),1)
    handle.set_options(90,False,False).set_ease(api.Ease.LINEAR).set_auto_kill(False).force_init()
    options = copy(handle.plug_options)
    options.snapping = snapping
    handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,.5,
        handle.start_value,Vector2(change_angle,0),1,False,0,api.UpdateNotice.NONE)
    assert tuple(values[-1]) == pytest.approx(expected,abs=1e-7,rel=0)
    assert not handle.plug_options.snapping and handle.change_value.x == 90
    manager.clear()


@pytest.mark.parametrize('kind',['quaternion','circle'])
def test_plugin_custom_ease_receives_the_explicit_elapsed_and_duration(kind):
    manager,values,calls = api.TweenManager(),[],[]
    def ease(t,d,a,p):
        calls.append((t,d))
        return t/d
    if kind == 'quaternion':
        handle = manager.add(QuaternionTweener(quatf.identity,values.append,quatf(0,0,1,0),1))
        expected = (0,0,sin(pi/8),cos(pi/8))
    else:
        handle = manager.to(api.CirclePlugin.get(),lambda:Vector2(0,1),values.append,Vector2(0,0),1)
        handle.set_options(90,False,False)
        expected = (sin(pi/8),cos(pi/8))
    handle.set_ease(ease).set_auto_kill(False).force_init()
    handle.get_plugin().evaluate_and_apply(handle.plug_options,handle,False,handle.getter,handle.setter,.5,
        handle.start_value,handle.change_value,2,False,0,api.UpdateNotice.NONE)
    assert calls == [(.5,2)]
    assert tuple(values[-1]) == pytest.approx(expected,abs=4e-7,rel=0)
    manager.clear()


def test_direct_quaternion_easing_captures_the_passed_values_before_callback():
    manager,values = api.TweenManager(),[]
    first,last = quatf.identity(),quatf(0,0,1,0)
    def ease(t,d,a,p):
        first.x,last.z = 1,.5
        return t/d
    handle = manager.add(QuaternionTweener(quatf.identity,values.append,last,1))
    handle.set_ease(ease).set_auto_kill(False).force_init()
    handle.get_plugin().evaluate_and_apply(handle.plug_options,handle,False,handle.getter,handle.setter,.5,
        first,last,1,False,0,api.UpdateNotice.NONE)
    assert tuple(values[-1]) == pytest.approx((0,0,sqrt(.5),sqrt(.5)),abs=4e-7,rel=0)
    manager.clear()


def test_direct_circle_easing_captures_the_passed_options_and_change():
    manager,values = api.TweenManager(),[]
    def ease(t,d,a,p):
        options.snapping = True
        change.x = 180
        return t/d
    handle = manager.to(api.CirclePlugin.get(),lambda:Vector2(0,1),values.append,Vector2(0,0),1)
    handle.set_options(90,False,False).set_ease(ease).set_auto_kill(False).force_init()
    options,change = copy(handle.plug_options),Vector2(90,0)
    for expected in ((sqrt(.5),sqrt(.5)),(1,0)):
        handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,.5,
            handle.start_value,change,1,False,0,api.UpdateNotice.NONE)
        assert tuple(values[-1]) == pytest.approx(expected,abs=4e-7,rel=0)
    manager.clear()


def test_explicit_time_sampler_is_reused_and_rebound_on_configuration_changes():
    manager = api.TweenManager()
    handle = manager.to(lambda:0.,lambda value:None,1.,1.).set_ease(api.Ease.LINEAR)
    assert '_ease_time' not in handle.__dict__
    first = handle._ease_time
    assert first(.5,2) == .25 and handle._ease_time is first
    handle.set_ease(api.Ease.IN_QUAD)
    assert '_ease_time' not in handle.__dict__
    second = handle._ease_time
    assert second(.5,2) == .0625 and second is not first
    assert first(.5,2) == .25
    manager.clear()
