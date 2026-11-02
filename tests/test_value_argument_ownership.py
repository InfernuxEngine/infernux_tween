"""Value arguments are captured before callbacks and own independent channels."""
import pytest

from infernux.lib import Vector2, Vector3, vec4f, quatf
from infernux.screen import Rect
import infernux_tween as api


KINDS = [(list, 4), (Vector2, 2), (Vector3, 3), (vec4f, 4), (Rect, 4)]
OPERATIONS = [
    ('from_now', [4,5,6,7], [10,13,16,19], [0,0,0,0], [7,9,11,13], 0),
    ('from_deferred', [4,5,6,7], [10,13,16,19], [0,0,0,0], [7,9,11,13], 0),
    ('from_relative', [6,8,10,12], [12,16,20,24], [0,0,0,0], [9,12,15,18], 1),
    ('change_start_new', [4,5,6,7], [10,13,16,19], [6,8,10,12], [7,9,11,13], 0),
    ('change_end_new', [2,3,4,5], [20,23,26,29], [18,20,22,24], [11,13,15,17], 1),
    ('change_both_new', [4,5,6,7], [20,23,26,29], [16,18,20,22], [12,14,16,18], 0),
    ('change_start_ready', [4,5,6,7], [10,13,16,19], [6,8,10,12], [7,9,11,13], 1),
    ('change_end_snap', [2,3,4,5], [20,23,26,29], [18,20,22,24], [11,13,15,17], 2),
    ('change_both_ready', [4,5,6,7], [20,23,26,29], [16,18,20,22], [12,14,16,18], 1),
]


@pytest.mark.parametrize('constructor,count', KINDS)
@pytest.mark.parametrize('operation,start,end,change,result,reads', OPERATIONS)
def test_inputs_are_copied_before_getter_and_do_not_alias_later_edits(
        constructor, count, operation, start, end, change, result, reads):
    def make(values):
        return list(values) if constructor is list else constructor(*values[:count])
    def edit(value, component):
        if constructor is Rect:
            return Rect(component, value.y, value.width, value.height)
        if constructor is list:
            value[0] = component
        else:
            value.x = component
        return value
    manager = api.TweenManager()
    current = [make([2,3,4,5])]
    first, last = make([4,5,6,7]), make([20,23,26,29])
    state = {'armed':False, 'reads':0}
    def getter():
        nonlocal first, last
        state['reads'] += 1
        if state['armed']:
            state['armed'] = False
            first, last = edit(first, 50), edit(last, 100)
        return current[0]
    # Declares the vector contract without an ambiguous quaternion read.
    getter.__annotations__['return'] = constructor
    handle = manager.to(getter, lambda v:current.__setitem__(0,v), make([10,13,16,19]), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).pause()
    if operation.endswith('_ready') or operation == 'change_end_snap':
        handle.force_init()
    state['armed'] = True
    if operation.startswith('from_'):
        handle.from_(first, operation != 'from_deferred', operation == 'from_relative')
    elif operation.startswith('change_start'):
        handle.change_start_value(first)
    elif operation == 'change_end_new':
        handle.change_end_value(last)
    elif operation == 'change_end_snap':
        handle.change_end_value(last, True)
    else:
        handle.change_values(first, last)
    assert tuple(handle.start_value) == tuple(start[:count])
    assert tuple(handle.end_value) == tuple(end[:count])
    assert tuple(handle.change_value) == tuple(change[:count])
    first, last = edit(first, 200), edit(last, 400)
    handle.goto(.5)
    assert tuple(current[0]) == tuple(result[:count])
    assert state['reads'] == reads
    manager.clear()


@pytest.mark.parametrize('annotation', [Vector3, 'Vector3', 'infernux.lib.Vector3'])
def test_explicit_vector_from_does_not_read_a_declared_getter(annotation):
    def getter():
        raise AssertionError('Explicit non-relative From has no need to read the target')
    getter.__annotations__['return'] = annotation
    manager, output = api.TweenManager(), []
    handle = manager.to(getter, output.append, Vector3(10,20,30), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).from_(Vector3(2,4,6))
    handle.goto(.5)
    assert tuple(output[0]) == (2,4,6)
    assert tuple(output[-1]) == (6,12,18)
    manager.clear()


def test_untyped_euler_getter_still_discovers_rotation_and_copies_its_argument():
    first, output = Vector3(0,30,0), []
    def getter():
        first.y = 150
        return quatf.identity()
    manager = api.TweenManager()
    handle = manager.to(getter, output.append, Vector3(0,90,0), 1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).from_(first)
    handle.goto(.5)
    assert tuple(output[0]) == pytest.approx(tuple(quatf.euler(0,30,0)), abs=4e-7, rel=0)
    assert tuple(output[-1]) == pytest.approx(tuple(quatf.euler(0,60,0)), abs=4e-7, rel=0)
    manager.clear()


def test_rect_keeps_the_entry_setter_when_custom_easing_replaces_it():
    manager, output, state = api.TweenManager(), [], {'armed':False}
    def ease(t,d,a,p):
        if state['armed']:
            state['armed'] = False
            handle.setter = lambda v:output.append(('replacement', tuple(v)))
        return t/d
    handle = manager.to(lambda:Rect(2,3,4,5),lambda v:output.append(('original',tuple(v))),Rect(10,13,16,19),1)
    handle.set_ease(ease).set_auto_kill(False).force_init()
    state['armed'] = True
    handle.goto(.5)
    handle.goto(.75)
    assert output == [('original',(6,8,10,12)),('replacement',(8,10.5,13,15.5))]
    manager.clear()


@pytest.mark.parametrize('kind,count', [(list,4),(Vector2,2),(Vector3,3),(vec4f,4)])
def test_from_setter_cannot_mutate_the_tweens_stored_start(kind, count):
    def make(values):
        return list(values) if kind is list else kind(*values[:count])
    seen = []
    def setter(value):
        seen.append(tuple(value))
        if kind is list:
            value[0] = 999
        else:
            value.x = 999
    manager = api.TweenManager()
    handle = manager.to(lambda:make([2,3,4,5]),setter,make([10,13,16,19]),1)
    handle.set_ease(api.Ease.LINEAR).set_auto_kill(False).from_()
    assert tuple(handle.start_value) == (10,13,16,19)[:count]
    handle.goto(.5)
    assert seen == [(10,13,16,19)[:count],(6,8,10,12)[:count]]
    manager.clear()
