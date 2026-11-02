"""Live UI owners, viewport geometry and native field transfers stay coherent."""
import numpy as np
import pytest

from infernux.batch import batch_read, batch_write, create_component_batch_handle
from infernux.components.fields import get_raw_field_value
from infernux.components import serialized_field
from infernux.lib import Vector2, Vector3
from infernux.ui import UICanvas, UIImage, UIButton, ScreenAlignH, ScreenAlignV
from infernux.lib import GameObject
import infernux_tween as tween
from test_links import owner


def widget(owner):
    scene, obj = owner
    root = scene.create_game_object('Canvas')
    canvas = root.add_component(UICanvas)
    canvas.reference_width, canvas.reference_height = 800, 600
    obj.set_parent(root, False)
    image = obj.add_component(UIImage)
    image.set_rect(100, 150, 200, 80, 800, 600)
    return canvas, image


@pytest.mark.parametrize('horizontal', list(ScreenAlignH))
@pytest.mark.parametrize('vertical', list(ScreenAlignV))
def test_binding_preserves_authored_screen_rect_and_actual_pose(owner, horizontal, vertical):
    canvas, image = widget(owner)
    image.align_h, image.align_v = horizontal, vertical
    image.pivot = Vector2(.25, .75)
    before = image.get_rect(800, 600), tuple(image.transform.local_position)
    _ = image.rect_transform
    assert image.get_rect(800, 600) == pytest.approx(before[0])
    assert tuple(image.transform.local_position) == before[1]


def test_stretch_uses_parent_frame_and_preview_does_not_edit_scene(owner):
    canvas, image = widget(owner)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta, image.anchored_position = Vector2(-20, -30), Vector2(0, 0)
    assert image.get_rect(800, 600) == (10, 15, 780, 570)
    assert (image.width, image.height) == (780, 570)
    before = image.transform.serialize_document()
    assert image.get_rect(1600, 1200) == (10, 15, 1580, 1170)
    assert image.transform.serialize_document() == before
    canvas.reference_width, canvas.reference_height = 1600, 1200
    assert (image.width, image.height) == (1580, 1170)


def test_raw_serialized_values_and_same_owner_visuals_share_native_geometry(owner):
    canvas, image = widget(owner)
    button = image.game_object.add_component(UIButton)
    _ = image.rect_transform
    assert button.width == image.width == 200
    button.width = 250
    image.rect_transform.pivot = Vector2(.25, .75)
    assert get_raw_field_value(image, 'width') == 250
    assert tuple(get_raw_field_value(button, 'pivot')) == (.25, .75)
    document = image._serialize_fields_document()
    assert document['width'] == 250


def test_native_parent_edits_refresh_child_geometry_even_without_python_assignment(owner):
    canvas, image = widget(owner)
    child_object = owner[0].create_game_object('Child')
    child_object.set_parent(image.game_object, False)
    child = child_object.add_component(UIImage)
    child.anchor_min = child.anchor_max = Vector2(.5, .5)
    child.anchored_position = Vector2(0, 0)
    before = child.get_rect(800, 600)
    image.rect_transform.anchored_position += Vector2(25, 10)
    after = child.get_rect(800, 600)
    assert after == pytest.approx((before[0] + 25, before[1] - 10, *before[2:]))


def test_world_rect_uses_pixels_for_layout_and_scene_units_for_pose(owner):
    scene, obj = owner
    obj.transform.local_position = Vector3(2, 3, 4)
    image = obj.add_component(UIImage)
    image.anchored_position3d = Vector3(250, 350, 450)
    assert tuple(obj.transform.local_position) == pytest.approx((2.5, 3.5, 4.5))
    obj.transform.local_position = Vector3(1, 2, 3)
    assert tuple(image.anchored_position3d) == pytest.approx((100, 200, 300))
    saved = obj.transform.serialize_document()
    assert saved['rect_layout']['position_scale'] == pytest.approx(.01)
    image.anchored_position = Vector2(1000, 1000)
    assert obj.transform.deserialize_document(saved)
    assert tuple(image.anchored_position3d) == pytest.approx((100, 200, 300))


@pytest.mark.parametrize('field,dtype,values', [
    ('width', np.float64, [250, 300]),
    ('pivot', np.float32, [[.25, .75], [0, 1]]),
    ('anchored_position', np.float32, [[12, 34], [56, 78]]),
])
def test_component_batch_and_scalar_fields_use_same_owner(owner, field, dtype, values):
    canvas, image = widget(owner)
    obj = owner[0].create_game_object('Other image')
    obj.set_parent(canvas.game_object, False)
    other = obj.add_component(UIImage)
    images = [image, other]
    handle = create_component_batch_handle(images, field)
    expected = np.asarray(values, dtype=dtype)
    handle.write(expected)
    np.testing.assert_array_equal(handle.read(), expected)
    np.testing.assert_array_equal(batch_read(images, field), expected)
    setattr(image, field, 175 if field == 'width' else Vector2(.5, .5))
    assert handle.read()[0] == pytest.approx(getattr(image, field))
    batch_write(images, expected, field)
    np.testing.assert_array_equal(handle.read(), expected)


def test_set_rect_round_trips_after_native_binding_and_at_other_viewport(owner):
    canvas, image = widget(owner)
    _ = image.rect_transform
    image.set_rect(75, 125, 100, 90, 1600, 1200)
    assert image.get_rect(1600, 1200) == pytest.approx((75, 125, 100, 90))


def test_cloned_ui_hierarchy_restores_canonical_fields_before_visual_reads(owner):
    canvas, image = widget(owner)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta, image.anchored_position = Vector2(-20, -30), Vector2(12, 34)
    copied = GameObject.instantiate(canvas.game_object)
    other = copied.get_child(0).get_component(UIImage)
    assert tuple(other.size_delta) == (-20, -30)
    assert tuple(other.anchored_position) == (12, 34)
    assert other.get_rect(800, 600) == image.get_rect(800, 600)
    other.width = 100
    assert image.width == 780


def test_nonvisual_hierarchy_nodes_transmit_rectangle_and_transform_offset(owner):
    canvas, image = widget(owner)
    bridge = owner[0].create_game_object('Grouping object')
    bridge.set_parent(canvas.game_object, False)
    bridge.transform.local_position = Vector3(20, 10, 0)
    image.game_object.set_parent(bridge, False)
    image.anchor_min = image.anchor_max = Vector2(.5, .5)
    image.size_delta, image.anchored_position = Vector2(40, 20), Vector2(0, 0)
    assert image.get_rect(800, 600) == (400, 280, 40, 20)
    bridge.transform.local_position += Vector3(15, 5, 0)
    assert image.get_rect(800, 600) == (415, 275, 40, 20)


@pytest.mark.parametrize('factory,field,end,expected', [
    (tween.twn_anchor_pos_x, 'anchored_position', 20, (35, -7)),
    (tween.twn_anchor_pos_y, 'anchored_position', 20, (15, 13)),
    (tween.twn_anchor_pos3d_z, 'anchored_position3d', 20, (15, -7, 23)),
])
def test_relative_from_preserves_unselected_axes_on_actual_ui(owner, factory, field, end, expected):
    canvas, image = widget(owner)
    image.anchored_position3d = Vector3(15, -7, 3)
    handle = factory(image, end, 1).set_ease(tween.Ease.LINEAR).set_relative().from_(True)
    handle.goto(0)
    assert tuple(getattr(image, field)) == expected


def test_size_delta_tween_changes_delta_of_stretched_geometry(owner):
    canvas, image = widget(owner)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta = Vector2(-20, -30)
    handle = tween.twn_size_delta(image, Vector2(-40, -50), 1).set_ease(tween.Ease.LINEAR)
    handle.goto(.5)
    assert tuple(image.size_delta) == (-30, -40)
    assert (image.width, image.height) == (770, 560)


def test_widget_default_overrides_keep_native_storage_and_other_fields_keep_cds(owner):
    from infernux.components._cds_bridge import get_class_info
    class CustomImage(UIImage):
        width: float = 256.
        height: float = serialized_field(default=128.)
    obj = owner[1]
    image = obj.add_component(CustomImage)
    assert (image.width, image.height) == (256, 128)
    info = get_class_info(CustomImage)
    assert 'width' not in info[1] and 'height' not in info[1] and 'pivot' not in info[1]
    assert 'opacity' in info[1]
    image.rect_transform.size_delta = Vector2(80, 40)
    assert (image.width, image.height) == (80, 40)


@pytest.mark.parametrize('kind', ['punch', 'shake'])
def test_planar_impulses_leave_independent_depth_edits_untouched(owner, kind):
    canvas, image = widget(owner)
    image.anchored_position3d = Vector3(15, -7, 3)
    handle = (tween.twn_punch_anchor_pos(image, Vector2(20, 30), 1) if kind == 'punch' else
              tween.twn_shake_anchor_pos(image, 1, Vector2(20, 30)))
    handle.set_auto_kill(False).goto(.25)
    image.anchored_position3d = Vector3(*image.anchored_position, 9)
    handle.goto(.5)
    assert image.anchored_position3d.z == 9
    handle.goto(1)
    assert tuple(image.anchored_position3d) == (15, -7, 9)


def test_circle_updates_anchored_position_and_keeps_depth(owner):
    canvas, image = widget(owner)
    image.anchored_position3d = Vector3(10, 0, 3)
    tween.twn_shape_circle(image, Vector2(0, 0), 180, 1).set_ease(tween.Ease.LINEAR).goto(1)
    assert tuple(image.anchored_position3d) == pytest.approx((0, -10, 3), abs=2e-5)


def test_restoring_plain_transform_and_fields_releases_old_layout_binding(owner):
    canvas, image = widget(owner)
    pose, fields = image.transform.serialize_document(), image._serialize_fields_document()
    _ = image.rect_transform
    image.width = 300
    assert image.transform.deserialize_document(pose)
    image._deserialize_fields_document(fields)
    assert '_native_rect_layout' not in image.__dict__
    assert (image.width, image.height) == (200, 80)
    _ = image.rect_transform
    assert image.get_rect(800, 600) == pytest.approx((100, 150, 200, 80))
