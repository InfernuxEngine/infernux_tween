"""Resolved container layout publishes one pose shared by scene and UI users."""
import pytest

from infernux.components.fields import get_raw_field_value
from infernux.lib import Vector2, Vector3
from infernux.ui import UICanvas, UIFrame, UIImage, UILayoutDirection, UILayoutSizing
from infernux.ui._layout_driver import rebuild_canvas
from test_links import owner


def group(owner, *, world=False):
    scene, frame_object = owner
    canvas = None
    if not world:
        root = scene.create_game_object('Canvas')
        canvas = root.add_component(UICanvas)
        canvas.reference_width, canvas.reference_height = 400, 300
        frame_object.set_parent(root, False)
    frame = frame_object.add_component(UIFrame)
    frame.width, frame.height = 300, 100
    frame.layout_direction, frame.gap = UILayoutDirection.Horizontal, 10
    frame.padding_left, frame.padding_top = 10, 5
    if canvas is not None:
        frame.set_rect(20, 30, 300, 100, 400, 300)
    else:
        frame.transform.position = Vector3(2, 3, 0)
    children = []
    for index, size in enumerate(((40, 30), (50, 20))):
        obj = scene.create_game_object('Child ' + str(index))
        obj.set_parent(frame_object, False)
        image = obj.add_component(UIImage)
        image.width, image.height = size
        children.append(image)
    for widget in (frame, *children):
        _ = widget.rect_transform
    return canvas, frame, children


def test_flow_rectangles_publish_real_local_pose_and_keep_scene_document_stable(owner):
    canvas, frame, (first, second) = group(owner)
    before = owner[0].serialize_document()
    assert frame.rebuild_layout()
    assert tuple(first.transform.local_position) == (-120, 30, 0)
    assert tuple(second.transform.local_position) == (-65, 35, 0)
    assert first.get_rect(400, 300) == (30, 35, 40, 30)
    assert second.get_rect(400, 300) == (80, 35, 50, 20)
    assert owner[0].serialize_document() == before
    revision = first.rect_transform.revision
    assert not rebuild_canvas(canvas)
    assert first.rect_transform.revision == revision


def test_viewport_and_fill_publish_live_dimensions_without_changing_authored_width(owner):
    canvas, frame, (first, second) = group(owner)
    frame.anchor_min, frame.anchor_max = Vector2(0, 0), Vector2(1, 1)
    frame.size_delta, frame.anchored_position = Vector2(-40, -60), Vector2(0, 0)
    second.width_sizing = UILayoutSizing.Fill
    before = owner[0].serialize_document()
    frame.rebuild_layout(800, 600)
    assert (frame.width, frame.height) == (760, 540)
    assert second.width == 700
    assert get_raw_field_value(second, 'width') == 50
    assert tuple(second.rect_transform.rect)[2:] == (700, 20)
    assert owner[0].serialize_document() == before
    current = tuple(second.transform.local_position)
    second.get_rect(400, 300)
    assert tuple(second.transform.local_position) == current
    second.width_sizing = UILayoutSizing.Fixed
    frame.rebuild_layout(800, 600)
    assert second.width == 50


def test_disabling_flow_releases_driver_and_restores_authored_pose(owner):
    canvas, frame, children = group(owner)
    original = [child.transform.serialize_document() for child in children]
    frame.rebuild_layout()
    frame.layout_direction = UILayoutDirection.None_
    frame.rebuild_layout()
    for child, document in zip(children, original):
        assert child.rect_transform._driver is None
        assert child.transform.serialize_document() == document
        assert tuple(child.transform.local_position) == (0, 0, 0)


def test_new_ui_binding_in_live_viewport_keeps_the_authored_reference_position(owner):
    canvas, frame, children = group(owner)
    canvas.rebuild_layout(800, 600)
    obj = owner[0].create_game_object('Late image')
    obj.set_parent(canvas.game_object, False)
    image = obj.add_component(UIImage)
    image.width, image.height = 40, 20
    from infernux.ui import ScreenAlignH
    image.align_h = ScreenAlignH.Right
    before = image.get_rect(800, 600)
    _ = image.rect_transform
    assert image.get_rect(800, 600) == pytest.approx(before)
    assert image.transform.serialize_document()['position'] == [0, 0, 0]


def test_world_layout_uses_scene_pose_and_parent_rotation(owner):
    canvas, frame, (first, second) = group(owner, world=True)
    before = owner[0].serialize_document()
    frame.rebuild_layout()
    assert tuple(first.transform.local_position) == pytest.approx((-1.2, .3, 0))
    assert tuple(first.transform.position) == pytest.approx((.8, 3.3, 0))
    assert owner[0].serialize_document() == before
    frame.transform.local_euler_angles = Vector3(0, 0, 90)
    assert tuple(first.transform.position) == pytest.approx((1.7, 1.8, 0), abs=2e-5)


def prepare(canvases, elements=(), measure=None, width=800, height=600, submission=None):
    from types import SimpleNamespace
    from infernux.engine.runtime_screen_ui import RuntimeScreenUISubmission
    submission = submission if submission is not None else SimpleNamespace()
    renderer = SimpleNamespace(measure_text=measure or (lambda *_args: (40, 20)))
    RuntimeScreenUISubmission._prepare_native_layouts(submission, tuple(canvases), tuple(elements),
                                                    renderer, width, height)
    return submission


def test_runtime_publication_updates_flow_before_command_geometry_and_reuses_static_layout(owner):
    canvas, frame, (first, second) = group(owner)
    before = owner[0].serialize_document()
    submission = prepare([canvas])
    assert tuple(first.transform.local_position) == (-120, 30, 0)
    revision = first.rect_transform.revision
    prepare([canvas], submission=submission)
    assert first.rect_transform.revision == revision
    frame.gap = 25
    prepare([canvas], submission=submission)
    assert tuple(second.transform.local_position) == (-50, 35, 0)
    # Only the authored gap changed, never the children's serialized positions.
    after = owner[0].serialize_document()
    frame.gap = 10
    assert owner[0].serialize_document() == before
    assert after != before


def test_runtime_text_reflows_after_flow_width_assignment_in_the_same_submission(owner):
    import math
    from infernux.ui import UIText, TextResizeMode
    canvas, frame, (first, second) = group(owner)
    text_owner = first.game_object
    text_owner.remove_component(first)
    text = text_owner.add_component(UIText)
    text.width, text.height, text.text = 200, 15, 'wrapped content'
    text.width_sizing = UILayoutSizing.Fill
    text.resize_mode = TextResizeMode.AutoHeight
    calls = []

    def measure(content, font_size, wrap, *_args):
        calls.append((content, wrap))
        return min(300, wrap), math.ceil(300 / wrap) * 20

    # An authoring tool can force geometry before a renderer exists. Runtime
    # publication must still resolve the first font measurement in this frame.
    canvas.rebuild_layout(400, 300)
    assert text.__dict__.get('_text_intrinsic_size') is None
    prepare([canvas], measure=measure, width=400, height=300)
    assert text.width == 230
    assert text.height == 40
    assert calls == [('wrapped content', 230)]
    assert tuple(text.rect_transform.rect)[2:] == (230, 40)
    text.text = 'updated'
    prepare([canvas], measure=measure, width=400, height=300)
    assert calls[-1][0] == 'updated'
    assert len(calls) == 2


def test_auto_text_drives_one_axis_and_releases_it_when_mode_changes(owner):
    from infernux.ui import UIText, TextResizeMode
    canvas, frame, children = group(owner)
    obj = owner[0].create_game_object('Intrinsic text')
    obj.set_parent(canvas.game_object, False)
    text = obj.add_component(UIText)
    text.width, text.height = 120, 30
    text.resize_mode = TextResizeMode.AutoWidth
    _ = text.rect_transform
    before = text._serialize_fields_document(), text.transform.serialize_document()
    prepare([canvas], measure=lambda *_args: (75, 18), width=400, height=300)
    assert (text.width, text.height) == (75, 30)
    assert (text._serialize_fields_document(), text.transform.serialize_document()) == before
    text.height = 50
    prepare([canvas], measure=lambda *_args: (75, 18), width=400, height=300)
    assert (text.width, text.height) == (75, 50)
    text.resize_mode = TextResizeMode.FixedSize
    prepare([canvas])
    assert (text.width, text.height) == (120, 50)
    assert text.rect_transform._driver is None


def test_runtime_world_publication_caches_membership_and_releases_inactive_children(owner):
    _, frame, (first, second) = group(owner, world=True)
    elements = (frame, first, second)
    submission = prepare([], elements)
    membership = frame.__dict__['_layout_elements']
    assert first.rect_transform._driver is frame.transform
    second.game_object.active = False
    prepare([], elements, submission=submission)
    assert frame.__dict__['_layout_elements'] is membership
    assert second.rect_transform._driver is None


def test_canvas_release_restores_viewport_and_all_layout_owned_channels(owner):
    from infernux.ui._layout_driver import release_layout
    canvas, frame, children = group(owner)
    before = owner[0].serialize_document()
    canvas.rebuild_layout(800, 600)
    assert release_layout(canvas)
    assert canvas.transform._rect_layout._driver is None
    for child in children:
        assert child.rect_transform._driver is None
    assert tuple(canvas.transform._rect_layout.rect)[2:] == (400, 300)
    assert owner[0].serialize_document() == before


def test_world_pointer_bounds_follow_native_dimensions_without_a_python_field_notification(owner):
    from infernux.engine.runtime_screen_ui import WorldUIElementTarget
    from infernux.ui.inx_ui_screen_component import _get_layout_revision
    _, frame, (first, second) = group(owner, world=True)
    target = WorldUIElementTarget(first)
    assert target.input_logical_size == (40, 30)
    python_revision = _get_layout_revision()
    first.rect_transform.size_delta = Vector2(90, 70)
    assert _get_layout_revision() == python_revision
    assert target.input_logical_size == (90, 70)
    assert target.raycast(85, 65) is first
    assert first.rect_transform._drive_rect(frame.transform, Vector2(25, 20), Vector2(0, 0))
    assert target.input_logical_size == (25, 20)
    assert target.raycast(85, 65) is None
