from types import SimpleNamespace

import numpy as np
import pytest

from infernux.lib import TextGeometryLayer, Vector3, quatf
from infernux_tween import TextTweenAnimator, Ease, LoopType, RotateMode
from infernux_tween.text import SkewSpanMode
import infernux_tween as tween_api


class Buffer:
    def __init__(self, count):
        self.character_count = count
        self.offsets = np.zeros((count, 2), dtype=np.float32)
        self.rotations = np.zeros(count, dtype=np.float32)
        self.scales = np.ones((count, 2), dtype=np.float32)
        self.skews = np.zeros(count, dtype=np.float32)
        self.colors = np.ones((count, 4, 4), dtype=np.float32)
        self.vertex_offsets = np.zeros((count, 4, 2), dtype=np.float32)
        self.affine_transforms = np.zeros((count, 3, 4), dtype=np.float32)
        self.vertex_depth_offsets = np.zeros((count, 4), dtype=np.float32)
        self.color_overrides = np.zeros(count, dtype=np.float32)
        self.affine_transforms[:, :, :3] = np.eye(3)

    def reset(self):
        for name in ("offsets", "rotations", "skews", "vertex_offsets", "vertex_depth_offsets", "affine_transforms", "color_overrides"):
            getattr(self, name).fill(0)
        self.scales.fill(1)
        self.colors.fill(1)
        self.affine_transforms[:, :, :3] = np.eye(3)


def layout(count=4):
    return SimpleNamespace(words=[SimpleNamespace(character_start=0, character_end=min(count, 2))],
                           lines=[object(), object()], glyphs=[SimpleNamespace(visible=True, color=(1, 1, 1, 1)) for _ in range(count)],
                           characters=[SimpleNamespace(line=i//2, glyph_start=i, glyph_end=i+1,
                                                       bounds=(i*12, 0, i*12+10, 20)) for i in range(count)])


def vector(value):
    return tuple(value)


@pytest.fixture
def text():
    uploads, resets = [], []
    target = SimpleNamespace(layout=layout(), color=[1, 1, 1, 1])
    target.get_text_layout = lambda: target.layout
    target.create_character_buffer = lambda: Buffer(len(target.layout.characters))
    target.set_character_data = lambda buffer, layer: uploads.append(layer)
    target.reset_character_data = lambda layer: resets.append(layer)
    try:
        yield target, uploads, resets
    finally:
        tween_api.clear()


def test_character_and_range_sequence_share_one_upload_per_update(text):
    target, uploads, resets = text
    animator = TextTweenAnimator(target)
    sequence = tween_api.sequence().set_auto_kill(False)
    for index in (0, 1):
        sequence.join(animator.do_offset_char(index, Vector3(10, 20, 30), 1).set_ease(Ease.LINEAR))
    sequence.join(animator.range(0, 2).do_fade(0, 1).set_ease(Ease.LINEAR))
    tween_api.update(0.5)
    assert uploads == [TextGeometryLayer.Manual]
    assert np.all(animator.buffer.affine_transforms[:2, :, 3] == (5, -10, 15))
    assert np.all(animator.buffer.offsets == 0)
    assert np.all(animator.buffer.colors[:2, :, 3] == 0.5)
    assert np.all(animator.buffer.colors[:, :, :3] == 1)
    sequence.pause()
    tween_api.update(0.2)
    assert len(uploads) == 1
    sequence.rewind()
    assert np.all(animator.buffer.affine_transforms[:, :, 3] == 0) and np.all(animator.buffer.colors == 1)
    animator.dispose()
    assert set(uploads+resets) == {TextGeometryLayer.Manual}


def test_character_relative_from_speed_and_killed_sequence_child(text):
    target, uploads, _ = text
    animator = TextTweenAnimator(target)
    animator.set_char_offset(0, Vector3(1, 2, 3))
    move = animator.do_offset_char(0, Vector3(3, 4, 0), 2).set_relative().set_ease(Ease.LINEAR).set_speed_based()
    move.force_init()
    assert move.duration() == pytest.approx(2.5)
    move.goto(1.25)
    assert vector(animator.get_char_offset(0)) == pytest.approx((2.5, 4, 3))
    move.kill()
    scale = animator.do_scale_char(1, 0, 1).from_().set_ease(Ease.LINEAR)
    assert vector(animator.get_char_scale(1)) == (0, 0, 0)
    scale.complete()
    assert vector(animator.get_char_scale(1)) == (1, 1, 1)
    dead = animator.do_rotate_char(0, Vector3(0, 0, 90), 1).set_ease(Ease.LINEAR)
    live = animator.do_rotate_char(1, Vector3(0, 0, 60), 1).set_ease(Ease.LINEAR)
    sequence = tween_api.sequence().join(dead).join(live)
    tween_api.update(0.25)
    dead.kill()
    stopped = animator.get_char_rotation(0)
    tween_api.update(0.25)
    assert vector(animator.get_char_rotation(0)) == pytest.approx(vector(stopped))
    assert vector(animator.get_char_rotation(1)) == pytest.approx((0, 0, 30))
    sequence.kill()


def test_character_group_explicit_from_and_value_changes_keep_one_shared_buffer(text):
    target, uploads, _ = text
    animator = TextTweenAnimator(target)
    tween = animator.range(0, 2).do_scale(2, 1).from_(0.25, False).set_ease(Ease.LINEAR).set_auto_kill(False)
    assert np.all(animator.buffer.affine_transforms[:, :, :3] == np.eye(3))
    tween.goto(0.5)
    assert np.all(animator.buffer.affine_transforms[:2, :, :3] == np.eye(3)*1.125)
    assert np.all(animator.buffer.affine_transforms[2:, :, :3] == np.eye(3))
    tween.change_values(0.5, 1.5)
    assert np.all(animator.buffer.affine_transforms[:2, :, :3] == np.eye(3)*0.5)
    tween.goto(0.5)
    assert np.all(animator.buffer.affine_transforms[:, :, :3] == np.eye(3))
    assert set(uploads) == {TextGeometryLayer.Manual}
    tween.kill()
    snapped = animator.range(0, 2).do_offset(Vector3(2, 4, 6), 1).set_options(True).from_(Vector3(0.2, 0.6, 1.2))
    assert np.all(animator.buffer.affine_transforms[:2, :, 3] == (0, -1, 1))
    snapped.kill()
    faded = animator.range(0, 2).do_color((0, 0, 0, 1), 1).set_options(True).from_(0.5).set_ease(Ease.LINEAR)
    assert np.all(animator.buffer.colors[:2, :, :3] == 1)
    assert np.all(animator.buffer.colors[:2, :, 3] == 0.5)
    assert np.all(animator.buffer.color_overrides[:2] == 2)
    faded.goto(0.5)
    assert np.all(animator.buffer.colors[:2, :, 3] == 0.75)
    faded.kill()


def test_layout_revision_retires_old_indices_and_preserves_other_layers(text):
    target, uploads, resets = text
    animator = TextTweenAnimator(target)
    tween = animator.word(0).do_offset(Vector3(10, 0, 1), 1)
    tween_api.update(0.2)
    target.layout = layout(1)
    tween_api.update(0.2)
    assert not tween.is_active()
    assert animator.buffer.character_count == 1
    assert len(uploads) == 1
    fresh = animator.line(0).do_color((1, 0, 0, 0.5), 1).set_ease(Ease.LINEAR)
    tween_api.update(1)
    assert np.all(animator.buffer.colors[:, :, 0] == 1)
    assert np.all(animator.buffer.colors[:, :, 1:3] == 0)
    assert set(uploads+resets) == {TextGeometryLayer.Manual}
    animator.reset()
    old = animator.do_offset_char(0, Vector3(2, 3, 4), 1)
    replacement = TextTweenAnimator(target)
    assert animator._disposed and not old.is_active()
    replacement.set_char_offset(0, Vector3(5, 6, 7))
    replacement.apply()
    old_resets = len(resets)
    assert animator.dispose() is None and animator.reset() is None
    assert len(resets) == old_resets
    assert tuple(replacement.get_char_offset(0)) == (5, 6, 7)
    with pytest.raises(RuntimeError, match="disposed"):
        animator.refresh()
    assert TextTweenAnimator.dispose_instance_for(target) is None
    assert replacement._disposed
    assert TextTweenAnimator.dispose_instance_for(target) is None
    original, spawned = TextTweenAnimator(target), []

    def create_during_kill():
        current = TextTweenAnimator(target)
        spawned.append(current)
        current.do_offset_char(0, Vector3(0, 0, 4), 1)

    pending = original.do_offset_char(0, Vector3(4, 0, 0), 1).on_kill(create_during_kill)
    outer = TextTweenAnimator(target)
    assert original._disposed and outer._disposed and not pending.is_active()
    assert len(spawned) == 1 and not spawned[0]._disposed
    assert TextTweenAnimator._instances[id(target)] is spawned[0]
    tween_api.update(1)
    assert tuple(spawned[0].get_char_offset(0)) == (0, 0, 4)
    TextTweenAnimator.dispose_instance_for(target)


def test_faulted_root_is_retired_without_repeating_callback_side_effects(text):
    target, uploads, _ = text
    animator, events = TextTweenAnimator(target), []
    def fail():
        events.append("attempt")
        raise RuntimeError("Failed user action")
    sequence = tween_api.sequence().append(animator.do_scale_char(0, 2, 0.5)).append_callback(fail)
    healthy = animator.do_offset_char(1, Vector3(4, 0, 2), 1).set_ease(Ease.LINEAR)
    with pytest.raises(RuntimeError, match="Failed user action"):
        tween_api.update(0.5)
    assert not sequence.is_active() and events == ["attempt"]
    assert len(uploads) == 1
    tween_api.update(1)
    assert events == ["attempt"] and not healthy.is_active()
    assert vector(animator.get_char_offset(1)) == pytest.approx((4, 0, 2))


def test_xyz_affine_and_accumulated_corner_depth_use_native_coordinate_convention(text):
    target, uploads, _ = text
    animator = TextTweenAnimator(target)
    offset, rotation, scale = Vector3(3, 5, 7), Vector3(23, 41, 59), Vector3(2, 3, 4)
    assert animator.set_char_offset(0, offset) is None
    assert animator.set_char_rotation(0, rotation) is None
    assert animator.set_char_scale(0, scale) is None
    affine = animator.buffer.affine_transforms[0]
    axes = np.array((1, -1, 1))
    native_rotation = quatf.euler(*rotation)
    for point in (Vector3(1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, 1), Vector3(2, -3, 4)):
        scaled = np.array(tuple(point))*axes*np.array(tuple(scale))
        rotated = native_rotation*quatf(*scaled, 0)*quatf.inverse(native_rotation)
        expected = (np.array((rotated.x, rotated.y, rotated.z))+tuple(offset))*axes
        assert affine[:, :3]@np.array(tuple(point))+affine[:, 3] == pytest.approx(expected, abs=2e-5)
    assert vector(animator.get_char_rotation(0)) == pytest.approx(vector(rotation), abs=2e-5)
    shifts = tuple(Vector3(i, i+1, i+2) for i in range(4))
    for _ in range(2):
        assert animator.shift_char_vertices(0, *shifts) is None
    expected = np.array([tuple(shifts[i]) for i in (0, 1, 3, 2)])*axes*2
    assert animator.buffer.vertex_offsets[0] == pytest.approx(expected[:, :2])
    assert animator.buffer.vertex_depth_offsets[0] == pytest.approx(expected[:, 2])
    animator.set_char_scale(0, Vector3(0, 0, 0))
    assert np.all(animator.buffer.affine_transforms[0, :, :3] == 0)
    assert animator.buffer.vertex_depth_offsets[0] == pytest.approx(expected[:, 2])
    assert animator.reset_vertices_shift(0) is None
    assert np.all(animator.buffer.vertex_offsets == 0) and np.all(animator.buffer.vertex_depth_offsets == 0)
    assert animator.reset() is None and animator.refresh() is None and animator.dispose() is None
    assert uploads and np.all(animator.buffer.affine_transforms[:, :, :3] == np.eye(3))


def test_invisible_and_invalid_characters_are_noops_and_spans_include_the_last_index(text):
    target, uploads, _ = text
    target.layout.glyphs[1].visible = False
    animator = TextTweenAnimator(target)
    for index in (-1, 1, 4):
        assert animator.do_offset_char(index, Vector3(1, 2, 3), 1) is None
        assert animator.do_rotate_char(index, Vector3(4, 5, 6), 1) is None
        assert animator.do_scale_char(index, 2, 1) is None
        assert animator.set_char_offset(index, Vector3(1, 2, 3)) is None
        assert animator.set_char_color(index, [0, 0, 0, 0]) is None
        assert vector(animator.get_char_scale(index)) == (0, 0, 0)
        assert animator.get_char_color(index) == [1, 1, 1, 1]
    assert not uploads
    with pytest.raises(ValueError):
        animator.character(4)
    with pytest.raises(TypeError, match="Vector3"):
        animator.set_char_offset(0, (1, 2, 3))
    assert animator.skew_char_x(0, 3, False) == 3
    assert animator.skew_char_y(0, 4) == 2
    assert animator.skew_char_y(2, 4, False, True) == 4
    animator.reset()
    assert animator.skew_span_x(0, 2, 2) is None
    assert np.all(animator.buffer.vertex_offsets[[0, 2], :2, 0] == 2)
    assert np.all(animator.buffer.vertex_offsets[[1, 3]] == 0)
    animator.reset()
    assert animator.skew_span_y(0, 2, 8, SkewSpanMode.AS_MAX_SKEW_FACTOR) is None
    amount = 8*20/34*0.5
    assert animator.buffer.vertex_offsets[0, [1, 2], 1] == pytest.approx((-amount, -amount))
    assert animator.get_char_offset(2).y == pytest.approx(amount*2.4)
    assert animator.buffer.vertex_offsets[2, 1, 1]+animator.buffer.affine_transforms[2, 1, 3] == pytest.approx(-8)
    assert np.all(animator.buffer.vertex_offsets[[1, 3]] == 0)
    with pytest.raises(TypeError, match="SkewSpanMode"):
        animator.skew_span_y(0, 2, 2, "Default")


def test_character_motion_uses_the_shared_clock_one_upload_and_exact_rest_values(text):
    target, uploads, _ = text
    animator = TextTweenAnimator(target)
    punch = animator.do_punch_char_offset(0, Vector3(2, 4, 6), 1, 2, 0.5).set_auto_kill(False)
    shake = animator.do_shake_char_scale(1, 1, 0.5, 4, 90, True).set_auto_kill(False)
    rotation = animator.do_shake_char_rotation(2, 1, Vector3(20, 30, 40), 4, 90, True).set_auto_kill(False)
    punch.from_(Vector3(90, 90, 90))
    assert not uploads
    tween_api.update(0.125)
    assert len(uploads) == 1
    assert vector(animator.get_char_offset(0)) == pytest.approx((1.53125, 3.0625, 4.59375))
    assert animator.get_char_scale(1).z != 1 and animator.get_char_rotation(2).z != 0
    retained = animator.buffer.affine_transforms.copy()
    for tween in (punch, shake, rotation):
        tween.goto(0.125, True)
    assert animator.buffer.affine_transforms == pytest.approx(retained)
    tween_api.update(0.875)
    assert vector(animator.get_char_offset(0)) == pytest.approx((0, 0, 0), abs=1e-6)
    assert vector(animator.get_char_scale(1)) == pytest.approx((1, 1, 1))
    assert vector(animator.get_char_rotation(2)) == pytest.approx((0, 0, 0), abs=1e-5)
    assert animator.do_punch_char_scale(0, 1, 0) is None
    with pytest.raises(TypeError, match="Vector3"):
        animator.do_shake_char_rotation(0, 1, 2)


def test_parent_incremental_rotation_mode_color_and_range_value_changes_share_settings(text):
    target, uploads, _ = text
    animator = TextTweenAnimator(target)
    animator.set_char_rotation(0, Vector3(0, 0, 350))
    rotate = animator.do_rotate_char(0, Vector3(0, 0, 10), 1, RotateMode.FAST).set_ease(Ease.LINEAR)
    scale = animator.do_scale_char(1, Vector3(2, 3, 4), 1).set_ease(Ease.LINEAR)
    batch = animator.range(2, 2).do_offset(Vector3(1, 2, 3), 1).set_ease(Ease.LINEAR)
    sequence = tween_api.sequence().join(rotate).join(scale).join(batch).set_loops(2, LoopType.INCREMENTAL)
    tween_api.update(1.5)
    assert len(uploads) == 2  # immediate rotation setter, then the shared frame commit
    assert animator.get_char_rotation(0).z == pytest.approx(20, abs=2e-5)
    assert vector(animator.get_char_scale(1)) == pytest.approx((2.5, 4, 5.5))
    assert animator.buffer.affine_transforms[2:, :, 3] == pytest.approx(np.array([[1.5, -3, 4.5]]*2))
    sequence.kill()
    color = animator.do_color_char(0, [0, 0.5, 1, 0.25], 1).set_ease(Ease.LINEAR)
    alpha = animator.do_fade_char(1, 0, 1).from_(0.5).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert animator.get_char_color(0) == pytest.approx([0.5, 0.75, 1, 0.625])
    assert animator.get_char_color(1) == pytest.approx([1, 1, 1, 0.25])
    color.kill()
    alpha.kill()
    target.color = [0.5, 1, 0.25, 0]
    target.layout.glyphs[0].color = [1, 0, 0, 0.5]
    animator.refresh()
    assert animator.get_char_color(0) == [0.5, 0, 0, 0]
    animator.set_char_offset(0, Vector3(1, 2, 3))
    assert np.all(animator.buffer.color_overrides == 0) and np.all(animator.buffer.colors == 1)
    fade = animator.do_fade_char(0, 1, 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert animator.buffer.color_overrides[0] == 2
    assert animator.get_char_color(0) == [0.5, 0, 0, 0.5]
    target.color = [0, 1, 1, 0]
    assert animator.get_char_color(0) == [0, 0, 0, 0.5]
    animator.set_char_color(0, [0, 1, 0, 0.75])
    assert animator.buffer.color_overrides[0] == 3
    assert animator.get_char_color(0) == [0, 1, 0, 0.75]
    tween_api.update(0.25)
    assert animator.buffer.color_overrides[0] == 3
    assert animator.get_char_color(0) == [0, 1, 0, 0.75]
    fade.kill()
    animator.reset()
    assert np.all(animator.buffer.color_overrides == 0)
    assert animator.get_char_color(0) == [0, 0, 0, 0]
