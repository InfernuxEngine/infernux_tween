"""Typed start keywords share parsing while preserving their value semantics."""
import pytest

from infernux.lib import Vector2, Vector3, quatf
import infernux_tween as tween


@pytest.mark.parametrize('immediate', [False, True])
@pytest.mark.parametrize('relative', [False, True])
def test_circle_degree_keyword_matches_its_positional_start(immediate, relative):
    manager = tween.TweenManager()
    first, second = [Vector2(1, 0)], [Vector2(1, 0)]
    def make(values):
        return manager.to(tween.CirclePlugin.get(), lambda: values[0], lambda value: values.__setitem__(0, value),
                          Vector2(0, 0), 1.).set_options(90., False).set_ease(tween.Ease.LINEAR).set_auto_kill(False)
    positional, named = make(first), make(second)
    try:
        positional.from_(180., immediate, relative)
        assert named.from_(from_value_degrees=180., set_immediately=immediate, is_relative=relative) is named
        assert tuple(first[0]) == tuple(second[0])
        if not immediate:
            assert tuple(second[0]) == (1., 0.)
        for delta in (.125, .375, .5):
            manager.update(delta)
            assert tuple(first[0]) == tuple(second[0])
        assert positional.is_complete() and named.is_complete()
    finally:
        manager.clear()


def test_typed_start_names_do_not_change_other_value_kinds():
    manager = tween.TweenManager()
    scalar = manager.to(lambda: 0., lambda value: None, 1., 1.)
    rotation = manager.to(lambda: quatf.identity(), lambda value: None, Vector3(0, 90, 0), 1.)
    try:
        with pytest.raises(TypeError):
            scalar.from_(from_alpha_value=.5)
        with pytest.raises(TypeError):
            rotation.from_(from_value_degrees=30.)
    finally:
        manager.clear()
