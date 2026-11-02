"""Shared native geometry through real UI layout, picking and Slider input."""

from types import SimpleNamespace

import pytest
from infernux.lib import Vector3
from infernux.lib import Vector2
from infernux.ui import UICanvas, UISlider, PointerEventData
from test_links import owner


def make_slider(owner):
    scene, obj = owner
    canvas_obj = scene.create_game_object('Geometry canvas')
    canvas = canvas_obj.add_component(UICanvas)
    canvas.reference_width, canvas.reference_height = 800, 600
    obj.set_parent(canvas_obj)
    slider = obj.add_component(UISlider)
    slider.width, slider.height = 120., 40.
    slider.minimum, slider.maximum = 0., 1.
    slider.set_rect(100., 200., 120., 40., 800., 600.)
    return slider


def test_geometry_snapshot_is_shared_and_refreshes_for_pose_and_size(owner):
    slider = make_slider(owner)
    first = slider._resolved_rect_geometry(800, 600)
    assert slider._resolved_rect_geometry(800, 600) is first
    before = [tuple(p) for p in first.corners]
    slider.transform.local_position += Vector3(10, 30, 0)
    second = slider._resolved_rect_geometry(800, 600)
    assert second is not first
    for a, b in zip(before, second.corners):
        assert tuple(b) == pytest.approx((a[0] + 10, a[1] - 30))
    assert [tuple(p) for p in first.corners] == before
    slider.width = 160
    third = slider._resolved_rect_geometry(800, 600)
    assert third is not second and third.rect[2] == 160
    assert slider._resolved_rect_geometry(800, 600) is third


@pytest.mark.parametrize('degrees', [0., .0001, 30., 90., 137., -90., 450.])
@pytest.mark.parametrize('pivot', [(.5, .5), (0, 1), (.25, .75), (-.2, 1.2)])
def test_slider_input_and_hit_geometry_share_the_rendered_rectangle(owner, degrees, pivot):
    slider = make_slider(owner)
    slider.pivot = Vector2(*pivot)
    slider.transform.local_euler_angles = Vector3(0, 0, degrees)
    geometry = slider._resolved_rect_geometry(800, 600)
    for actual, expected in zip(slider.get_rotated_corners(800, 600), geometry.corners):
        assert actual == tuple(expected)
    assert slider.get_visual_rect(800, 600) == tuple(geometry.visual_rect)
    event = PointerEventData()
    event.canvas = slider.get_canvas()
    event.canvas_size = (800, 600)
    for fraction in (.1, .25, .75, .9):
        event.position = geometry.to_canvas((120 * fraction, 20))
        assert slider.contains_point(*event.position, 800, 600)
        slider._set_from_pointer(event)
        assert slider.value == pytest.approx(fraction, abs=2e-6)
    outside = geometry.to_canvas((-10, 20))
    assert not slider.contains_point(*outside, 800, 600)
    assert slider.contains_point(*outside, 800, 600, tolerance=11)


def test_world_pointer_context_is_already_projected_into_the_ui_plane(owner):
    slider = make_slider(owner)
    slider.transform.local_euler_angles = Vector3(0, 0, 80)
    event = PointerEventData()
    event.canvas = SimpleNamespace(element_rect=lambda _: (0, 0, 120, 40))
    event.canvas_size = (800, 600)
    event.position = (90, 20)
    slider._set_from_pointer(event)
    assert slider.value == pytest.approx(.75)


@pytest.mark.parametrize('pivot', [(0, 1), (.25, .75), (1, 0), (-.2, 1.2)])
def test_world_pointer_projection_and_editor_frame_use_the_authored_pivot(owner, pivot):
    from infernux.engine.runtime_screen_ui import map_world_ui_ray
    from infernux.engine.ui.ui_rect_manipulation import resolve_world_ui_frame
    slider = make_slider(owner)
    slider.game_object.set_parent(None, False)
    slider.pivot = Vector2(*pivot)
    slider.transform.position = Vector3(1, 2, 3)
    target = SimpleNamespace(element=slider, game_object=slider.game_object, input_logical_size=(120, 40))
    point = map_world_ui_ray(target, Vector3(1, 2, 4), Vector3(0, 0, -1))
    assert point[:2] == pytest.approx((120 * pivot[0], 40 * (1 - pivot[1])), abs=2e-5)
    frame = resolve_world_ui_frame(slider)
    assert frame['center'] == pytest.approx((1 + (.5 - pivot[0]) * 1.2,
                                           2 - (pivot[1] - .5) * .4, 3), abs=2e-6)
