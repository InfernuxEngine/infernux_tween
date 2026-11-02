"""Callbacks change the next invocation, not the current value-type arguments."""
import gc
import weakref

import pytest
from infernux.lib import Vector2, Vector3, vec4f, quatf
import infernux_tween as api
from infernux_tween.rotation import EulerTweener, RotateMode


@pytest.mark.parametrize('mode,first,second,setters', [
    ('ease_values', [6,8,10,12], [125,10.5,13,15.5], ['original','original']),
    ('ease_options', [6,8,10,12], [100,200,300,15.5], ['original','original']),
    ('getter_options', [100,200,300,12], [8,10.5,13,15.5], ['original','original']),
    ('ease_setter', [6,8,10,12], [8,10.5,13,15.5], ['original','replacement']),
])
def test_color_sampling_captures_values_options_and_delegates_before_callbacks(mode, first, second, setters):
    manager, values, calls, state = api.TweenManager(), [[2,3,4,5]], [], {'armed':False}
    def getter():
        if state['armed'] and mode=='getter_options':
            state['armed']=False
            handle.plug_options.alpha_only=False
        return values[0]
    def original(value): values[0]=value;calls.append('original')
    def replacement(value): values[0]=value;calls.append('replacement')
    def ease(t,d,a,p):
        if state['armed'] and mode.startswith('ease_'):
            state['armed']=False
            if mode=='ease_values':handle.start_value.r=50;handle.change_value.r=100
            if mode=='ease_options':handle.plug_options.alpha_only=True
            if mode=='ease_setter':handle.setter=replacement
        return t/d
    handle=manager.to(getter,original,[10,13,16,19],1).set_ease(ease).set_auto_kill(False).pause()
    handle.force_init()
    if mode=='getter_options':handle.plug_options.alpha_only=True
    values[0]=[100,200,300,0];state['armed']=True
    handle.goto(.5)
    assert values[0]==first
    values[0]=[100,200,300,0]
    handle.goto(.75)
    assert values[0]==second and calls==setters
    manager.clear()


@pytest.mark.parametrize('kind,channels', [(Vector2,2),(Vector3,3),(vec4f,4)])
def test_vector_component_edits_in_custom_ease_apply_on_the_next_sample(kind, channels):
    manager, values, state = api.TweenManager(), [], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed']=False
            handle.start_value.x,handle.change_value.x=50,100
        return t/d
    handle=manager.to(lambda:kind(*([2]*channels)),values.append,kind(*([10]*channels)),1)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    state['armed']=True
    handle.goto(.5)
    assert tuple(values[-1])==(6,)*channels
    handle.goto(.75)
    assert tuple(values[-1])==(125,)+(8,)*(channels-1)
    manager.clear()


def test_vector_axis_change_during_ease_keeps_current_axis_and_existing_deltas():
    manager, values, state = api.TweenManager(), [Vector3(2,3,4)], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed']=False
            handle.plug_options.axis_constraint=api.AxisConstraint.Y
        return t/d
    handle=manager.to(lambda:values[0],lambda v:values.__setitem__(0,v),Vector3(10,13,16),1)
    handle.set_options(api.AxisConstraint.X).set_ease(ease).set_auto_kill(False).force_init()
    values[0]=Vector3(100,200,300);state['armed']=True
    handle.goto(.5)
    assert tuple(values[0])==(6,200,300)
    values[0]=Vector3(100,200,300)
    handle.goto(.75)
    assert tuple(values[0])==(100,3,300)
    manager.clear()


def test_scalar_setter_replacement_during_ease_takes_effect_next_time():
    manager, values, state = api.TweenManager(), [], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed']=False
            handle.setter=lambda v:values.append(('replacement',v))
        return t/d
    handle=manager.to(lambda:2.,lambda v:values.append(('original',v)),10.,1.)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    state['armed']=True
    handle.goto(.5);handle.goto(.75)
    assert values==[('original',6),('replacement',8)]
    manager.clear()


def test_euler_value_edit_during_custom_ease_keeps_current_rotation_inputs():
    manager, values, state = api.TweenManager(), [], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed']=False
            handle.start_value.y=90
        return t/d
    handle=manager.add(EulerTweener(quatf.identity,values.append,Vector3(0,90,0),1,RotateMode.FAST))
    handle.set_ease(ease).set_auto_kill(False).force_init()
    state['armed']=True
    handle.goto(.5)
    assert tuple(values[-1])==pytest.approx(tuple(quatf.euler(0,45,0)),abs=4e-7,rel=0)
    handle.goto(.75)
    assert tuple(values[-1])==pytest.approx(tuple(quatf.euler(0,157.5,0)),abs=4e-7,rel=0)
    manager.clear()


def test_custom_native_bridge_keeps_python_callback_cycles_collectable():
    def create():
        manager=api.TweenManager()
        handle=manager.to(lambda:[0]*4,lambda v:None,[1]*4,1)
        handle.set_ease(lambda t,d,a,p: t/d + 0*handle.start_value.r).force_init()
        reference=weakref.ref(handle)
        manager.clear()
        return reference
    reference=create()
    gc.collect()
    assert reference() is None


def test_custom_native_bridge_reports_a_nonnumeric_ease_result_at_the_boundary():
    manager=api.TweenManager().init(use_safe_mode=False)
    handle=manager.to(lambda:[0]*4,lambda v:None,[1]*4,1).set_ease(lambda *args:'invalid')
    handle.force_init()
    with pytest.raises(TypeError):
        handle.goto(.5)
    manager.clear()


def test_array_setter_replacement_during_ease_applies_on_the_next_sample():
    manager, values, state=api.TweenManager(),[],{'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed']=False
            handle.setter=lambda v:values.append(('replacement',tuple(v)))
        return t/d
    handle=manager.to_array(Vector3,lambda v:values.append(('original',tuple(v))),[Vector3(2,4,6)],[1])
    handle.set_ease(ease).set_auto_kill(False).force_init()
    state['armed']=True
    handle.goto(.5);handle.goto(.75)
    assert values==[('original',(1,2,3)),('replacement',(1.5,3,4.5))]
    manager.clear()
