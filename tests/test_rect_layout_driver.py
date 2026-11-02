"""Layout writes publish live geometry while preserving authored scene input."""
import pytest

from infernux.lib import SceneManager, GameObject, Vector2, Vector3


@pytest.fixture
def scene():
    scenes = SceneManager.instance()
    current = scenes.create_scene('Driven rectangle state')
    try:
        yield current
    finally:
        scenes.unload_scene(current)


def rectangles(scene):
    parent, child = [scene.create_game_object(name) for name in ('Frame', 'Child')]
    frame = parent.transform._rect_layout
    frame.size_delta = Vector2(200, 100)
    child.set_parent(parent, False)
    layout = child.transform._rect_layout
    layout.anchor_min, layout.anchor_max = Vector2(0, 0), Vector2(1, 1)
    layout.pivot, layout.size_delta = Vector2(.25, .75), Vector2(-20, -10)
    layout.anchored_position3d = Vector3(10, -5, 3)
    return parent, child, frame, layout


def test_viewport_driver_updates_descendant_pose_without_changing_serialized_input(scene):
    parent, child, frame, layout = rectangles(scene)
    before = parent.transform.serialize_document(), child.transform.serialize_document()
    assert frame._drive_size(parent.transform, Vector2(400, 200))
    assert tuple(layout.rect)[2:] == (380, 190)
    assert tuple(child.transform.local_position) == (-90, 45, 3)
    assert tuple(layout._authoring_rect)[2:] == (180, 90)
    assert (parent.transform.serialize_document(), child.transform.serialize_document()) == before
    revision = frame.revision
    assert not frame._drive_size(parent.transform, Vector2(400, 200))
    assert frame.revision == revision
    assert frame._clear_driver(parent.transform)
    assert tuple(child.transform.local_position) == (-40, 20, 3)
    assert (parent.transform.serialize_document(), child.transform.serialize_document()) == before


def test_child_layout_driver_owns_only_xy_and_size_and_restores_authored_fields(scene):
    parent, child, frame, layout = rectangles(scene)
    before = child.transform.serialize_document()
    assert layout._drive_rect(parent.transform, Vector2(80, 40), Vector2(30, 10))
    assert tuple(child.transform.local_position) == (30, 10, 3)
    assert tuple(layout.rect)[2:] == (80, 40)
    assert layout._driver is parent.transform
    assert child.transform.serialize_document() == before
    layout._set_authoring_size(0, 120)
    assert tuple(layout.rect)[2:] == (80, 40)
    assert tuple(layout._authoring_rect)[2:] == (120, 90)
    assert not layout._clear_driver(child.transform)
    assert layout._clear_driver(parent.transform)
    assert layout._driver is None
    assert tuple(layout.rect)[2:] == (120, 90)
    assert tuple(layout.anchored_position3d) == (10, -5, 3)


def test_driver_claim_cannot_be_replaced_by_another_owner(scene):
    parent, child, frame, layout = rectangles(scene)
    layout._drive_rect(parent.transform, Vector2(80, 40), Vector2(30, 10))
    with pytest.raises(RuntimeError, match='another layout driver'):
        layout._drive_size(child.transform, Vector2(90, 50))
    assert tuple(layout.rect)[2:] == (80, 40)


def test_snapshot_preserves_live_driver_but_scene_document_does_not(scene):
    parent, child, frame, layout = rectangles(scene)
    layout._drive_rect(parent.transform, Vector2(80, 40), Vector2(30, 10))
    document, snapshot = child.transform.serialize_document(), child.transform._capture_rect_state()
    layout._drive_rect(parent.transform, Vector2(60, 70), Vector2(5, 6))
    assert child.transform.deserialize_document(document)
    assert layout._driver is None
    child.transform._restore_rect_state(snapshot)
    assert layout._driver is parent.transform
    assert tuple(child.transform.local_position) == (30, 10, 3)
    assert tuple(layout.rect)[2:] == (80, 40)
    assert child.transform.serialize_document() == document


def test_reparent_releases_previous_parent_driver(scene):
    parent, child, frame, layout = rectangles(scene)
    layout._drive_rect(parent.transform, Vector2(80, 40), Vector2(30, 10))
    other = scene.create_game_object('New frame')
    other.transform._rect_layout.size_delta = Vector2(300, 200)
    child.set_parent(other, False)
    assert layout._driver is None
    assert tuple(layout.anchored_position3d) == (10, -5, 3)
    assert tuple(layout.rect)[2:] == (280, 190)


def test_hierarchy_clone_copies_authored_layout_without_live_driver_ownership(scene):
    parent, child, frame, layout = rectangles(scene)
    frame._drive_size(parent.transform, Vector2(400, 200))
    layout._drive_rect(parent.transform, Vector2(80, 40), Vector2(30, 10))
    copied = GameObject.instantiate(parent)
    copied_child = copied.get_child(0)
    assert copied.transform._rect_layout._driver is None
    assert copied_child.transform._rect_layout._driver is None
    assert tuple(copied.transform._rect_layout.rect)[2:] == (200, 100)
    assert tuple(copied_child.transform._rect_layout.rect)[2:] == (180, 90)
    assert tuple(copied_child.transform.local_position) == (-40, 20, 3)


def test_axis_driver_preserves_updates_to_the_other_axis_and_restores_only_owned_channels(scene):
    parent, child, frame, layout = rectangles(scene)
    assert layout._drive_size(child.transform, Vector2(80, 500), 1)
    assert tuple(layout.rect)[2:] == (80, 90)
    layout._set_authoring_size(1, 130)
    assert tuple(layout.rect)[2:] == (80, 130)
    layout._drive_size(child.transform, Vector2(999, 60), 2)
    assert tuple(layout.rect)[2:] == (180, 60)
    assert tuple(layout._authoring_rect)[2:] == (180, 130)
    layout._clear_driver(child.transform)
    assert tuple(layout.rect)[2:] == (180, 130)


def test_driver_boundary_rejects_missing_owner(scene):
    parent, child, frame, layout = rectangles(scene)
    with pytest.raises(TypeError):
        layout._drive_size(None, Vector2(80, 50))
