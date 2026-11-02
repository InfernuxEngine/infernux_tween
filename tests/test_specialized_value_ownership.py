"""Specialized value arguments stay independent across observable callbacks."""
from math import sqrt

import pytest
from infernux.lib import Vector2, quatf
import infernux_tween as api
from infernux_tween.rotation import QuaternionTweener


def create(manager, kind, getter, setter):
    if kind == 'quaternion':
        return manager.add(QuaternionTweener(getter, setter, quatf(.2,.4,.6,.8), 1))
    return manager.to(api.CirclePlugin.get(), getter, setter, Vector2(.2,.4), 1).set_options(120,False,False)


@pytest.mark.parametrize('kind', ['quaternion','circle'])
@pytest.mark.parametrize('ready', [False,True])
def test_replacing_end_captures_its_channels_before_the_getter(kind, ready):
    manager = api.TweenManager()
    end = quatf(.8,.3,.2,.4) if kind == 'quaternion' else Vector2(.8,.3)
    current = quatf(.1,.2,.3,.9) if kind == 'quaternion' else Vector2(.1,.2)
    armed = False
    def getter():
        if armed:
            end.x = 10
        return current
    handle = create(manager,kind,getter,lambda value:None).set_auto_kill(False)
    if ready:
        handle.force_init()
    armed = True
    handle.change_end_value(end, True) if ready else handle.change_end_value(end)
    assert handle.end_value.x == pytest.approx(.8)
    end.x = 40
    assert handle.end_value.x == pytest.approx(.8)
    manager.clear()


@pytest.mark.parametrize('kind', ['quaternion','circle'])
def test_explicit_relative_from_captures_input_before_reading_the_target(kind):
    manager = api.TweenManager()
    first = quatf(.4,.5,.6,.7) if kind == 'quaternion' else Vector2(.4,.5)
    current = quatf(.1,.2,.3,.9) if kind == 'quaternion' else Vector2(.1,.2)
    def getter():
        first.x = 5
        return current
    handle = create(manager,kind,getter,lambda value:None).set_auto_kill(False)
    handle.from_(first,True,True)
    expected = (.4,.65,.72,.31) if kind == 'quaternion' else (.09860622882843018,.2007029801607132)
    assert tuple(handle.start_value) == pytest.approx(expected,abs=4e-7,rel=0)
    manager.clear()


@pytest.mark.parametrize('kind', ['quaternion','circle'])
def test_from_setter_receives_a_value_independent_of_stored_start(kind):
    manager = api.TweenManager()
    current = quatf(.1,.2,.3,.9) if kind == 'quaternion' else Vector2(.1,.2)
    def setter(value):
        value.x = 999
    handle = create(manager,kind,lambda:current,setter).set_auto_kill(False)
    handle.from_()
    expected = (.2,.4,.6,.8) if kind == 'quaternion' else (.393649160861969,.2881966233253479)
    assert tuple(handle.start_value) == pytest.approx(expected,abs=4e-7,rel=0)
    manager.clear()


def test_quaternion_component_edits_in_easing_affect_the_next_invocation():
    manager, values, state = api.TweenManager(), [], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed'] = False
            handle.start_value.x, handle.change_value.z = 1, .5
        return t/d
    handle = manager.add(QuaternionTweener(quatf.identity,values.append,quatf(0,0,1,0),1))
    handle.set_ease(ease).set_auto_kill(False).force_init()
    state['armed'] = True
    handle.goto(.5)
    assert tuple(values[-1]) == pytest.approx((0,0,sqrt(.5),sqrt(.5)),abs=4e-7,rel=0)
    handle.goto(.75)
    assert values[-1].x > .1
    manager.clear()


def test_circle_component_edits_in_easing_affect_the_next_invocation():
    manager, values, state = api.TweenManager(), [], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed'] = False
            handle.change_value.x = 180
            handle.plug_options.snapping = True
        return t/d
    handle = manager.to(api.CirclePlugin.get(),lambda:Vector2(0,1),values.append,Vector2(0,0),1)
    handle.set_options(90,False,False).set_ease(ease).set_auto_kill(False).force_init()
    state['armed'] = True
    handle.goto(.5)
    assert tuple(values[-1]) == pytest.approx((sqrt(.5),sqrt(.5)),abs=4e-7,rel=0)
    handle.goto(.75)
    assert tuple(values[-1]) == (1,-1)
    manager.clear()


@pytest.mark.parametrize('t,expected', [
    (0,(0,0,0,1)),
    (.25,(0,0,.07880477607250214,.996890127658844)),
    (.75,(0,0,.2364143282175064,.9716523289680481)),
    (1,(0,0,.31224992871284485,.949999988079071)),
])
def test_quaternion_near_parallel_branch_includes_the_threshold(t,expected):
    result = quatf.slerp(quatf.identity(),quatf(0,0,.31224992871284485,.949999988079071),t)
    assert tuple(result) == pytest.approx(expected,abs=4e-7,rel=0)


def test_spherical_branch_preserves_zero_quaternion_storage():
    assert tuple(quatf.slerp(quatf(0,0,0,0),quatf(0,0,0,0),.5)) == (0,0,0,0)
