"""Live rectangle animation follows its current Canvas and layout owner."""
import pytest

from infernux.lib import GameObject, Vector2, Vector3
from infernux.ui import UICanvas, UIFrame, UIImage, UILayoutDirection
import infernux_tween as tween
from test_links import owner
from test_ui_layout_publication import group


def canvas(scene, name, width, height):
    result = scene.create_game_object(name).add_component(UICanvas)
    result.reference_width, result.reference_height = width, height
    return result


def test_stretched_animation_reparents_into_a_fresh_canvas_without_a_render_tick(owner):
    scene, obj = owner
    first = canvas(scene, 'First Canvas', 800, 600)
    second = canvas(scene, 'Fresh Canvas', 1200, 800)
    obj.set_parent(first.game_object, False)
    image = obj.add_component(UIImage)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta, image.anchored_position = Vector2(-20, -30), Vector2(12, 34)
    layout = image.rect_transform
    handle = tween.twn_size_delta(image, Vector2(-60, -70), 1).set_ease(tween.Ease.LINEAR)
    handle.goto(.25)
    assert (image.width, image.height) == (770, 560)
    obj.set_parent(second.game_object, False)
    assert (image.width, image.height) == (1170, 760)
    assert image.get_canvas() is second
    assert image.rect_transform is layout
    assert tuple(image.anchored_position) == (12, 34)
    assert (image.width, image.height) == (1170, 760)
    handle.goto(.75)
    assert tuple(image.size_delta) == (-50, -60)
    assert (image.width, image.height) == (1150, 740)
    assert image.get_rect(1200, 800) == (37, -4, 1150, 740)
    first.reference_width = 1600
    assert image.width == 1150


@pytest.mark.parametrize('visual_parent', [False, True])
@pytest.mark.parametrize('depth', [1, 3])
@pytest.mark.parametrize('entry_point', ['game_object', 'transform'])
def test_live_animation_reparents_through_previously_unbound_containers(owner, visual_parent, depth, entry_point):
    scene, obj = owner
    first = canvas(scene, 'First Canvas', 800, 600)
    destination = canvas(scene, 'Destination Canvas', 1200, 800)
    obj.set_parent(first.game_object, False)
    image = obj.add_component(UIImage)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta, image.anchored_position = Vector2(-20, -30), Vector2(0, 0)
    handle = tween.twn_size_delta(image, Vector2(-60, -70), 1).set_ease(tween.Ease.LINEAR)
    handle.goto(.25)
    assert (image.width, image.height) == (770, 560)
    parent = destination.game_object
    for index in range(depth):
        bridge = scene.create_game_object(f'Unbound container {index}')
        bridge.set_parent(parent, False)
        parent = bridge
    if visual_parent:
        frame = parent.add_component(UIFrame)
        frame.width, frame.height = 300, 200
    assert not parent.transform._has_rect_layout
    if entry_point == 'game_object':
        obj.set_parent(parent, False)
    else:
        obj.transform.set_parent(parent.transform, False)
    # Query native-backed sizes before touching a Python Canvas/layout getter.
    width, height = (300, 200) if visual_parent else (1200, 800)
    assert (image.width, image.height) == (width - 30, height - 40)
    assert tuple(obj.transform.local_position) == (0, 0, 0)
    handle.goto(.75)
    assert (image.width, image.height) == (width - 50, height - 60)
    assert image.get_rect(1200, 800)[2:] == (width - 50, height - 60)


def test_transform_parent_assignment_preserves_world_pose_and_size_in_a_fresh_container(owner):
    scene, obj = owner
    first = canvas(scene, 'First Canvas', 800, 600)
    destination = canvas(scene, 'Destination Canvas', 1200, 800)
    obj.set_parent(first.game_object, False)
    image = obj.add_component(UIImage)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta, image.anchored_position3d = Vector2(-20, -30), Vector3(15, 25, 3)
    handle = tween.twn_size_delta(image, Vector2(-60, -70), 1).set_ease(tween.Ease.LINEAR)
    handle.goto(.25)
    before = tuple(obj.transform.position), (image.width, image.height)
    parent = scene.create_game_object('Fresh UI parent')
    parent.set_parent(destination.game_object, False)
    frame = parent.add_component(UIFrame)
    frame.width, frame.height = 300, 200
    parent.transform.local_position = Vector3(40, 50, 2)
    obj.transform.parent = parent.transform
    assert tuple(obj.transform.position) == pytest.approx(before[0])
    assert (image.width, image.height) == before[1]
    handle.goto(.75)
    assert (image.width, image.height) == (250, 140)


def test_parent_preparation_is_not_repeated_during_playback_or_for_static_siblings(owner, monkeypatch):
    scene, obj = owner
    first = canvas(scene, 'First Canvas', 800, 600)
    obj.set_parent(first.game_object, False)
    image = obj.add_component(UIImage)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta = Vector2(-20, -30)
    handle = tween.twn_size_delta(image, Vector2(-60, -70), 1).set_ease(tween.Ease.LINEAR)
    parent = scene.create_game_object('New parent')
    parent.set_parent(first.game_object, False)
    frame = parent.add_component(UIFrame)
    frame.width, frame.height = 300, 200
    sibling = scene.create_game_object('Static sibling')
    sibling.set_parent(parent, False)
    sibling.add_component(UIImage)
    before_sibling = sibling.serialize_document()
    calls = []
    prepare = frame._prepare_native_rect_layout
    def counted():
        calls.append(True)
        return prepare()
    monkeypatch.setattr(frame, '_prepare_native_rect_layout', counted)
    obj.set_parent(parent, False)
    assert len(calls) == 1
    for index in range(20):
        handle.goto(index / 20)
        assert image.width > 0
    obj.set_parent(first.game_object, False)
    obj.set_parent(parent, False)
    assert len(calls) == 1
    assert not sibling.transform._has_rect_layout
    assert sibling.serialize_document() == before_sibling


@pytest.mark.parametrize('component_type', [UIFrame, UIImage])
def test_adding_a_visual_to_an_existing_bridge_shares_its_native_rectangle(owner, component_type):
    scene, obj = owner
    root = canvas(scene, 'Canvas', 800, 600)
    parent = scene.create_game_object('Originally empty parent')
    parent.set_parent(root.game_object, False)
    obj.set_parent(parent, False)
    image = obj.add_component(UIImage)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta = Vector2(-20, -30)
    handle = tween.twn_size_delta(image, Vector2(-60, -70), 1).set_ease(tween.Ease.LINEAR)
    handle.goto(.25)
    assert parent.transform._has_rect_layout
    visual = parent.add_component(component_type)
    visual.width, visual.height = 300, 200
    assert (image.width, image.height) == (270, 160)
    assert (visual.width, visual.height) == (300, 200)
    handle.goto(.75)
    assert (image.width, image.height) == (250, 140)
    assert tuple(visual.rect_transform.rect)[2:] == (300, 200)


def test_ordinary_canvas_preparation_does_not_rewrite_unanimated_controls(owner):
    scene, obj = owner
    root = canvas(scene, 'Static Canvas', 800, 600)
    obj.set_parent(root.game_object, False)
    obj.add_component(UIImage)
    before = scene.serialize_document()
    for _ in range(3):
        assert not root._prepare_native_layout(None, 800, 600, 1)
    assert scene.serialize_document() == before
    assert not obj.transform._has_rect_layout


def test_live_anchor_animation_changes_units_with_its_screen_or_world_parent(owner):
    scene, obj = owner
    image = obj.add_component(UIImage)
    image.anchor_min = image.anchor_max = Vector2(.5, .5)
    image.anchored_position3d = Vector3(150, 75, 3)
    layout = image.rect_transform
    assert tuple(obj.transform.local_position) == pytest.approx((1.5, .75, .03))
    handle = tween.twn_anchor_pos3d(image, Vector3(250, 175, 7), 1).set_ease(tween.Ease.LINEAR)
    handle.goto(.25)
    destination = canvas(scene, 'Screen destination', 800, 600)
    obj.set_parent(destination.game_object, False)
    assert image.rect_transform is layout
    assert tuple(obj.transform.local_position) == pytest.approx((175, 100, 4))
    handle.goto(.75)
    assert tuple(obj.transform.local_position) == pytest.approx((225, 150, 6))
    obj.set_parent(None, False)
    assert tuple(obj.transform.local_position) == pytest.approx((2.25, 1.5, .06))
    assert tuple(image.anchored_position3d) == pytest.approx((225, 150, 6))
    handle.goto(1)
    assert tuple(obj.transform.local_position) == pytest.approx((2.5, 1.75, .07))


def test_preserving_world_pose_also_preserves_rectangle_corners_across_unit_changes(owner):
    scene, obj = owner
    image = obj.add_component(UIImage)
    image.anchor_min = image.anchor_max = Vector2(.5, .5)
    image.size_delta = Vector2(40, 20)
    image.anchored_position3d = Vector3(150, 75, 3)
    before = [tuple(point) for point in image.rect_transform.get_world_corners()]
    destination = canvas(scene, 'Screen destination', 800, 600)
    obj.set_parent(destination.game_object, True)
    assert (image.width, image.height) == pytest.approx((.4, .2))
    for current, expected in zip(image.rect_transform.get_world_corners(), before):
        assert tuple(current) == pytest.approx(expected)
    obj.set_parent(None, True)
    assert (image.width, image.height) == pytest.approx((40, 20))
    for current, expected in zip(image.rect_transform.get_world_corners(), before):
        assert tuple(current) == pytest.approx(expected)


def test_cloned_rectangle_retains_automatic_units_and_independent_state(owner):
    scene, obj = owner
    image = obj.add_component(UIImage)
    image.anchor_min = image.anchor_max = Vector2(.5, .5)
    image.anchored_position3d = Vector3(150, 75, 3)
    copied = GameObject.instantiate(obj)
    clone = copied.get_component(UIImage)
    destination = canvas(scene, 'Clone destination', 800, 600)
    copied.set_parent(destination.game_object, False)
    assert tuple(copied.transform.local_position) == pytest.approx((150, 75, 3))
    assert tuple(obj.transform.local_position) == pytest.approx((1.5, .75, .03))
    clone.anchored_position3d = Vector3(200, 100, 4)
    assert tuple(image.anchored_position3d) == pytest.approx((150, 75, 3))


def test_saved_rectangle_resolves_its_units_from_the_current_parent(owner):
    scene, obj = owner
    image = obj.add_component(UIImage)
    image.anchor_min = image.anchor_max = Vector2(.5, .5)
    image.anchored_position3d = Vector3(150, 75, 3)
    saved = obj.transform.serialize_document()
    destination = canvas(scene, 'Restore destination', 800, 600)
    obj.set_parent(destination.game_object, False)
    image.anchored_position3d = Vector3(200, 100, 4)
    assert obj.transform.deserialize_document(saved)
    assert tuple(image.anchored_position3d) == pytest.approx((150, 75, 3))
    assert tuple(obj.transform.local_position) == pytest.approx((150, 75, 3))


@pytest.mark.parametrize('visual_parent', [False, True])
def test_reparenting_a_bound_subtree_updates_descendant_units_without_python_queries(owner, visual_parent):
    scene, child = owner
    parent = scene.create_game_object('Moving UI subtree')
    if visual_parent:
        parent.add_component(UIFrame)
    child.set_parent(parent, False)
    image = child.add_component(UIImage)
    image.anchor_min = image.anchor_max = Vector2(.5, .5)
    image.anchored_position3d = Vector3(10, 5, 3)
    assert tuple(child.transform.local_position) == pytest.approx((.1, .05, .03))
    destination = canvas(scene, 'Subtree destination', 800, 600)
    parent.set_parent(destination.game_object, False)
    assert tuple(child.transform.local_position) == pytest.approx((10, 5, 3))
    parent.set_parent(None, False)
    assert tuple(child.transform.local_position) == pytest.approx((.1, .05, .03))


@pytest.mark.parametrize('rebuild_old_first', [False, True])
def test_old_flow_owner_cannot_release_the_new_parent_driver(owner, rebuild_old_first):
    scene, _ = owner
    original, old_frame, (image, _) = group(owner)
    old_frame.rebuild_layout()
    destination = canvas(scene, 'Destination Canvas', 500, 400)
    parent = scene.create_game_object('Destination Flow')
    parent.set_parent(destination.game_object, False)
    new_frame = parent.add_component(type(old_frame))
    new_frame.width, new_frame.height = 200, 100
    new_frame.layout_direction = UILayoutDirection.Horizontal
    new_frame.padding_left, new_frame.padding_top = 20, 10
    image.game_object.set_parent(parent, False)
    if rebuild_old_first:
        old_frame.rebuild_layout()
    new_frame.rebuild_layout()
    expected = tuple(image.transform.local_position), tuple(image.rect_transform.rect)
    assert image.rect_transform._driver is new_frame.transform
    old_frame.rebuild_layout()
    assert image.rect_transform._driver is new_frame.transform
    assert (tuple(image.transform.local_position), tuple(image.rect_transform.rect)) == expected
    new_frame.layout_direction = UILayoutDirection.None_
    new_frame.rebuild_layout()
    assert image.rect_transform._driver is None
