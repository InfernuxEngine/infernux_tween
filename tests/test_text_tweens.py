from types import SimpleNamespace

import numpy as np
import pytest

from infernux.lib import TextGeometryLayer
from infernux_tween import DOTween, DOTweenTextAnimator, Ease


class Buffer:
    def __init__(self, count):
        self.character_count = count
        self.offsets = np.zeros((count, 2), dtype=np.float32)
        self.rotations = np.zeros(count, dtype=np.float32)
        self.scales = np.ones((count, 2), dtype=np.float32)
        self.skews = np.zeros(count, dtype=np.float32)
        self.colors = np.ones((count, 4, 4), dtype=np.float32)
        self.vertex_offsets = np.zeros((count, 4, 2), dtype=np.float32)

    def reset(self):
        for name in ("offsets", "rotations", "skews", "vertex_offsets"):
            getattr(self, name).fill(0)
        self.scales.fill(1)
        self.colors.fill(1)


@pytest.fixture
def text():
    layout = SimpleNamespace(words=[SimpleNamespace(character_start=0, character_end=2)],
                             lines=[object(), object()], characters=[SimpleNamespace(line=i//2) for i in range(4)])
    uploads, resets = [], []
    target = SimpleNamespace(layout=layout)
    target.get_text_layout = lambda: target.layout
    target.create_character_buffer = lambda: Buffer(len(target.layout.characters))
    target.set_character_data = lambda buffer, layer: uploads.append(layer)
    target.reset_character_data = lambda layer: resets.append(layer)
    try:
        yield target, uploads, resets
    finally:
        DOTween.Clear()


def test_character_and_range_sequence_share_one_upload_per_update(text):
    target, uploads, resets = text
    animator = DOTweenTextAnimator(target)
    sequence = DOTween.Sequence().SetAutoKill(False)
    for index in (0, 1):
        sequence.Join(animator.DOOffsetChar(index, (10, 20), 1).SetEase(Ease.Linear))
    sequence.Join(animator.Range(0, 2).DOFade(0, 1).SetEase(Ease.Linear))
    DOTween.Update(0.5)
    assert uploads == [TextGeometryLayer.Manual]
    assert np.all(animator.buffer.offsets[:2] == (5, 10))
    assert np.all(animator.buffer.colors[:2, :, 3] == 0.5)
    assert np.all(animator.buffer.colors[:, :, :3] == 1)
    sequence.Pause()
    DOTween.Update(0.2)
    assert len(uploads) == 1
    sequence.Rewind()
    assert np.all(animator.buffer.offsets == 0) and np.all(animator.buffer.colors == 1)
    animator.Dispose()
    assert set(uploads+resets) == {TextGeometryLayer.Manual}


def test_character_relative_from_speed_and_killed_sequence_child(text):
    target, uploads, _ = text
    animator = DOTweenTextAnimator(target)
    animator.SetCharOffset(0, (1, 2))
    move = animator.DOOffsetChar(0, (3, 4), 2).SetRelative().SetEase(Ease.Linear).SetSpeedBased()
    move.ForceInit()
    assert move.Duration() == pytest.approx(2.5)
    move.Goto(1.25)
    assert animator.GetCharOffset(0) == pytest.approx((2.5, 4))
    move.Kill()
    scale = animator.DOScaleChar(1, 0, 1).From().SetEase(Ease.Linear)
    assert np.all(animator.GetCharScale(1) == 0)
    scale.Complete()
    assert np.all(animator.GetCharScale(1) == 1)
    dead = animator.DORotateChar(0, 90, 1).SetEase(Ease.Linear)
    live = animator.DORotateChar(1, 60, 1).SetEase(Ease.Linear)
    sequence = DOTween.Sequence().Join(dead).Join(live)
    DOTween.Update(0.25)
    dead.Kill()
    stopped = animator.GetCharRotation(0)
    DOTween.Update(0.25)
    assert animator.GetCharRotation(0) == stopped
    assert animator.GetCharRotation(1) == 30
    sequence.Kill()


def test_layout_revision_retires_old_indices_and_preserves_other_layers(text):
    target, uploads, resets = text
    animator = DOTweenTextAnimator(target)
    tween = animator.Word(0).DOOffset((10, 0), 1)
    DOTween.Update(0.2)
    target.layout = SimpleNamespace(characters=[SimpleNamespace(line=0)], words=[], lines=[object()])
    DOTween.Update(0.2)
    assert not tween.IsActive()
    assert animator.buffer.character_count == 1
    assert len(uploads) == 1
    fresh = animator.Line(0).DOColor((1, 0, 0, 0.5), 1).SetEase(Ease.Linear)
    DOTween.Update(1)
    assert np.all(animator.buffer.colors[:, :, 0] == 1)
    assert np.all(animator.buffer.colors[:, :, 1:3] == 0)
    assert set(uploads+resets) == {TextGeometryLayer.Manual}
    animator.Reset()
