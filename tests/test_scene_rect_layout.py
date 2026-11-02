"""Rectangle layout is a parameterization of live native scene transforms."""
import numpy as np
import pytest

from infernux.batch import batch_write, create_batch_handle
from infernux.lib import GameObject, SceneManager, Vector2, Vector3
from infernux.lib._Infernux import _UITransformDependencies


@pytest.fixture
def rect_scene():
    scenes = SceneManager.instance()
    scene = scenes.create_scene('Rectangle layout ownership')
    try:
        yield scene
    finally:
        scenes.unload_scene(scene)


def make_rects(scene):
    parent, owner = scene.create_game_object('Parent'), scene.create_game_object('Child')
    frame, layout = parent.transform._rect_layout, owner.transform._rect_layout
    frame.size_delta = Vector2(200, 100)
    owner.set_parent(parent, False)
    layout.anchor_min, layout.anchor_max = Vector2(0, 0), Vector2(1, 1)
    layout.pivot, layout.size_delta = Vector2(.25, .75), Vector2(-20, -10)
    layout.anchored_position3d = Vector3(10, -5, 3)
    return parent, owner, frame, layout


def test_parent_size_and_shared_views_keep_one_transform_pose(rect_scene):
    parent, owner, frame, layout = make_rects(rect_scene)
    another = owner.transform._rect_layout
    assert tuple(owner.transform.local_position) == (-40, 20, 3)
    assert tuple(layout.rect)[2:] == (180, 90)
    frame.size_delta = Vector2(400, 200)
    assert tuple(owner.transform.local_position) == (-90, 45, 3)
    assert tuple(another.anchored_position) == (10, -5)
    assert tuple(another.rect)[2:] == (380, 190)
    another.anchored_position = Vector2(20, 15)
    assert tuple(layout.anchored_position) == (20, 15)
    assert tuple(owner.transform.local_position) == (-80, 65, 3)


@pytest.mark.parametrize('mode', ['list', 'strict', 'compact'])
@pytest.mark.parametrize('property', ['position', 'local_position'])
def test_batch_position_writes_update_anchor_parameters(rect_scene, mode, property):
    parent, owner, frame, layout = make_rects(rect_scene)
    parent.transform.position = Vector3(20, -10, 0)
    transforms = [owner.transform]
    handle = transforms if mode == 'list' else create_batch_handle(transforms, mode=mode)
    batch_write(handle, np.asarray([[17, 23, -4]], dtype=np.float32), property)
    local = (17, 23, -4) if property == 'local_position' else (-3, 33, -4)
    assert tuple(owner.transform.local_position) == local
    assert tuple(layout.anchored_position3d) == (local[0] + 50, local[1] - 25, -4)
    frame.size_delta = Vector2(400, 200)
    assert tuple(owner.transform.local_position) == (local[0] - 50, local[1] + 25, -4)


def test_serialization_restores_parameters_and_pose_together(rect_scene):
    parent, owner, frame, layout = make_rects(rect_scene)
    document = owner.transform.serialize_document()
    before = [tuple(point) for point in layout.get_world_corners()]
    layout.pivot = Vector2(.8, -.2)
    layout.size_delta = Vector2(10, 20)
    layout.anchored_position = Vector2(-100, 150)
    assert owner.transform.deserialize_document(document)
    assert owner.transform.serialize_document() == document
    assert [tuple(point) for point in layout.get_world_corners()] == before


def test_hierarchy_clone_has_independent_layout_state(rect_scene):
    parent, owner, frame, layout = make_rects(rect_scene)
    copied = GameObject.instantiate(parent)
    cloned_child = copied.get_child(0)
    cloned = cloned_child.transform._rect_layout
    assert tuple(cloned.anchored_position3d) == tuple(layout.anchored_position3d)
    assert tuple(cloned.rect) == tuple(layout.rect)
    copied.transform._rect_layout.size_delta = Vector2(400, 200)
    assert tuple(cloned_child.transform.local_position) == (-90, 45, 3)
    assert tuple(owner.transform.local_position) == (-40, 20, 3)


def test_retained_view_rejects_destroyed_and_recycled_owner_slots(rect_scene):
    owner = rect_scene.create_game_object('Temporary')
    layout = owner.transform._rect_layout
    rect_scene.destroy_game_object(owner)
    rect_scene.process_pending_destroys()
    replacement = rect_scene.create_game_object('Replacement')
    replacement.transform._rect_layout.size_delta = Vector2(300, 200)
    with pytest.raises(RuntimeError, match='outlived'):
        _ = layout.rect


def test_geometry_dependencies_notice_resize_without_a_pose_change(rect_scene):
    owner = rect_scene.create_game_object('Stable pivot')
    layout = owner.transform._rect_layout
    dependency = _UITransformDependencies([owner], [])
    revision = dependency.poll()
    assert dependency.poll() == revision
    before = tuple(owner.transform.position)
    layout.size_delta = Vector2(240, 90)
    assert tuple(owner.transform.position) == before
    assert dependency.poll() > revision
    assert list(dependency.changed_entries) == [0]
    revision = dependency.poll()
    layout.size_delta = Vector2(240, 90)
    assert dependency.poll() == revision


def test_removing_parent_layout_refreshes_child_frame_and_restoring_rebuilds_it(rect_scene):
    parent, child, frame, layout = make_rects(rect_scene)
    with_layout = parent.transform.serialize_document()
    plain = dict(with_layout)
    plain.pop('rect_layout')
    assert parent.transform.deserialize_document(plain)
    assert tuple(child.transform.local_position) == (10, -5, 3)
    assert tuple(layout.rect)[2:] == (-20, -10)
    assert parent.transform.deserialize_document(with_layout)
    assert tuple(child.transform.local_position) == (-40, 20, 3)
    assert tuple(layout.rect)[2:] == (180, 90)
