"""Direct plugin calls capture value arguments while array storage stays live."""
from copy import copy
from math import cos, sin, pi

import numpy as np
import pytest
from infernux.lib import Vector2, Vector3, vec4f, quatf
from infernux.screen import Rect
import infernux_tween as api
from infernux_tween.rotation import EulerTweener, RotateMode


@pytest.mark.parametrize('make', [
    np.float32, np.float64, np.int32, np.int64, np.uint32, np.uint64,
    lambda v:Vector2(v,v), lambda v:Vector3(v,v,v), lambda v:vec4f(v,v,v,v),
    lambda v:[v]*4, lambda v:Rect(v,v,v,v),
])
def test_builtin_direct_ease_uses_supplied_seconds_without_retiming_the_owner(make):
    manager,values,calls=api.TweenManager(),[],[]
    def ease(t,d,a,p):calls.append((t,d));return t/d
    handle=manager.to(lambda:make(0),values.append,make(8),1)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    handle.get_plugin().evaluate_and_apply(handle.plug_options,handle,False,handle.getter,handle.setter,
        .5,handle.start_value,handle.change_value,2,False,0,api.UpdateNotice.NONE)
    assert calls==[(.5,2)]
    result=values[-1]
    components=[float(result)] if np.isscalar(result) else list(result)
    assert components==pytest.approx([2]*len(components))
    assert handle.duration()==1 and handle.elapsed()==0
    manager.clear()


@pytest.mark.parametrize('make', [Vector2,Vector3,vec4f,list,tuple])
def test_direct_vectors_capture_values_and_options_before_ease_and_getter(make):
    size={Vector2:2,Vector3:3,vec4f:4,list:3,tuple:3}[make]
    create=lambda v:make([v]*size) if make in (list,tuple) else make(*([v]*size))
    manager,values=api.TweenManager(),[]
    first,change=create(2),create(8)
    def ease(t,d,a,p):
        if isinstance(first,list):first[0]=50;change[0]=100
        elif make is not tuple:first.x,change.x=50,100
        options.axis_constraint,options.snapping=api.AxisConstraint.Y,True
        return t/d
    handle=manager.to(lambda:create(100),values.append,create(10),1)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    options=copy(handle.plug_options)
    handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,
        .5,first,change,2,False,0,api.UpdateNotice.NONE)
    assert tuple(values[-1])==pytest.approx([4]*size)
    manager.clear()


def test_direct_color_keeps_current_alpha_only_setting_when_getter_changes_it():
    manager,values=api.TweenManager(),[]
    def getter():options.alpha_only=False;return [100,200,300,400]
    handle=manager.to(lambda:[0]*4,values.append,[8]*4,1).set_ease(api.Ease.LINEAR)
    handle.set_auto_kill(False).force_init()
    options=copy(handle.plug_options);options.alpha_only=True
    handle.get_plugin().evaluate_and_apply(options,handle,False,getter,values.append,
        .5,[0]*4,[8]*4,2,False,0,api.UpdateNotice.NONE)
    assert values[-1]==[100,200,300,2]
    manager.clear()


@pytest.mark.parametrize('make',[np.float32,lambda v:Rect(v,v,v,v)])
def test_direct_snapping_option_is_fixed_before_custom_easing(make):
    manager,values=api.TweenManager(),[]
    def ease(t,d,a,p):options.snapping=True;return t/d
    handle=manager.to(lambda:make(0),values.append,make(8),1)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    options=copy(handle.plug_options)
    for expected in (1.75,2):
        handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,
            .5,make(1.2),make(2.2),2,False,0,api.UpdateNotice.NONE)
        actual=values[-1]
        assert (float(actual) if np.isscalar(actual) else actual.x)==pytest.approx(expected,abs=2e-7)
    manager.clear()


def test_direct_rich_text_captures_options_before_easing():
    manager,values,calls=api.TweenManager(),[],[]
    def ease(t,d,a,p):
        calls.append((t,d));options.rich_text_enabled=False
        return t/d
    handle=manager.to(lambda:'ab',values.append,'<b>ABCDEFGH</b>',1).set_options(True)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    options=copy(handle.plug_options)
    handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,
        .5,handle.start_value,handle.change_value,2,False,0,api.UpdateNotice.NONE)
    assert values==['<b>AB</b>'] and calls==[(.5,2)]
    assert not options.rich_text_enabled
    manager.clear()


def test_direct_euler_value_and_mode_edits_apply_on_the_next_call():
    manager,values=api.TweenManager(),[]
    first,change=Vector3(),Vector3(0,90,0)
    def ease(t,d,a,p):
        first.y,change.y=90,180
        options.rotate_mode=RotateMode.WORLD_AXIS_ADD
        return t/d
    handle=manager.add(EulerTweener(quatf.identity,values.append,Vector3(0,90,0),1))
    handle.set_ease(ease).set_auto_kill(False).force_init()
    options=copy(handle.plug_options)
    handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,
        .5,first,change,2,False,0,api.UpdateNotice.NONE)
    assert tuple(values[-1])==pytest.approx((0,sin(pi/16),0,cos(pi/16)),abs=2e-7,rel=0)
    manager.clear()


def test_direct_array_ease_keeps_shared_storage_but_uses_segment_seconds():
    manager,values,calls=api.TweenManager(),[],[]
    def ease(t,d,a,p):
        calls.append((t,d))
        handle.start_value[1].x,handle.change_value[1].x=100,120
        options.axis_constraint,options.snapping=api.AxisConstraint.X,True
        return t/d
    handle=manager.to_array(Vector3,values.append,[Vector3(4,8,12),Vector3(10,20,30)],[.4,.6])
    handle.set_ease(ease).set_auto_kill(False).force_init()
    options=copy(handle.plug_options)
    old_segment_duration=handle._segment_duration
    handle.get_plugin().evaluate_and_apply(options,handle,False,handle.getter,handle.setter,
        .5,handle.start_value,handle.change_value,2,False,0,api.UpdateNotice.NONE)
    assert len(calls)==1 and calls[0]==pytest.approx((.1,.6),abs=1e-7)
    assert tuple(values[-1])==pytest.approx((120,10,15),abs=2e-6)
    assert handle._segment_duration==old_segment_duration
    manager.clear()
