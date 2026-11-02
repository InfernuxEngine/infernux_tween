"""Native field batches retain the scalar scene ordering and buffer contracts."""
import numpy as np
import pytest

from infernux.lib import SceneManager, Vector2, Vector3
from infernux.lib._Infernux import _RectLayoutBatch


@pytest.fixture
def scene():
    scenes = SceneManager.instance()
    current = scenes.create_scene('Rectangle field batches')
    try:
        yield current
    finally:
        scenes.unload_scene(current)


def nodes(scene, prefix):
    objects = [scene.create_game_object(prefix + str(i)) for i in range(3)]
    layouts = [owner.transform._rect_layout for owner in objects]
    layouts[0].size_delta = Vector2(200, 100)
    objects[1].set_parent(objects[0], False)
    layouts[1].anchor_min = Vector2(0, 0)
    layouts[1].anchor_max = Vector2(1, 1)
    layouts[1].size_delta = Vector2(-20, -10)
    # The child precedes its parent: a batch must retain supplied write order.
    return [objects[i] for i in (1, 0, 2)], [layouts[i] for i in (1, 0, 2)]


FIELDS = ['width', 'height', 'pivot', 'anchor_min', 'anchor_max', 'size_delta',
          'anchored_position', 'anchored_position3d', 'offset_min', 'offset_max']


def get(layout, field):
    if field in ('width', 'height'):
        return layout.rect[2 if field == 'width' else 3]
    return tuple(getattr(layout, field))


def set(layout, field, value):
    if field in ('width', 'height'):
        layout.set_size_with_current_anchors(0 if field == 'width' else 1, float(value))
    else:
        setattr(layout, field, Vector3(*value) if field == 'anchored_position3d' else Vector2(*value))


@pytest.mark.parametrize('field', FIELDS)
def test_field_batches_match_sequential_scene_writes(scene, field):
    objects, layouts = nodes(scene, 'Batch')
    expected_objects, expected = nodes(scene, 'Scalar')
    batch = _RectLayoutBatch(layouts, field)
    shape = (3,) if batch.channels == 1 else (3, batch.channels)
    dtype = np.float64 if batch.channels == 1 else np.float32
    output = np.empty(shape, dtype=dtype)
    batch.read_into(output)
    np.testing.assert_array_equal(output, np.asarray([get(layout, field) for layout in expected], dtype=dtype))
    values = np.arange(1, output.size + 1, dtype=dtype).reshape(shape) * .25
    original = values.copy()
    values.flags.writeable = False
    batch.write(values)
    for layout, value in zip(expected, values):
        set(layout, field, value)
    batch.read_into(output)
    np.testing.assert_array_equal(output, np.asarray([get(layout, field) for layout in expected], dtype=dtype))
    np.testing.assert_array_equal(values, original)
    for actual, wanted in zip(objects, expected_objects):
        assert tuple(actual.transform.local_position) == tuple(wanted.transform.local_position)


def test_all_owner_generations_are_checked_before_a_write(scene):
    first, second = [scene.create_game_object(name) for name in ('First', 'Expired')]
    left, right = first.transform._rect_layout, second.transform._rect_layout
    batch = _RectLayoutBatch([left, right], 'width')
    scene.destroy_game_object(second)
    scene.process_pending_destroys()
    replacement = scene.create_game_object('Reused slot')
    replacement.transform._rect_layout.size_delta = Vector2(300, 200)
    with pytest.raises(RuntimeError, match='outlived'):
        batch.write(np.asarray([40, 50], dtype=np.float64))
    assert left.rect.z == 100
    assert replacement.transform._rect_layout.rect.z == 300


def test_buffer_validation_precedes_scene_changes_and_handles_unaligned_storage(scene):
    _, layouts = nodes(scene, 'Buffers')
    batch = _RectLayoutBatch(layouts, 'anchored_position')
    before = [tuple(layout.anchored_position) for layout in layouts]
    for invalid in (np.ones((3, 2), dtype=np.float64), np.ones((3, 4), dtype=np.float32)[:, ::2],
                    np.ones((2, 2), dtype=np.float32)):
        with pytest.raises(ValueError, match='typed row buffer'):
            batch.write(invalid)
        assert [tuple(layout.anchored_position) for layout in layouts] == before
    unaligned = np.ndarray((3, 2), dtype=np.float32, buffer=bytearray(25), offset=1)
    unaligned[:] = [[1, 2], [3, 4], [5, 6]]
    batch.write(unaligned)
    batch.read_into(unaligned)
    np.testing.assert_array_equal(unaligned, [[1, 2], [3, 4], [5, 6]])


def test_empty_typed_batches_do_not_require_an_owner(scene):
    for field, shape, dtype in [('width', (0,), np.float64), ('pivot', (0, 2), np.float32)]:
        batch = _RectLayoutBatch([], field)
        output = np.empty(shape, dtype=dtype)
        batch.read_into(output)
        batch.write(output)
