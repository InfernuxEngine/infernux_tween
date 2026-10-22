"""Character tweening in one native Manual layer, alongside persistent effects."""
from weakref import WeakSet

import numpy as np
from infernux.lib import TextGeometryLayer

from .core import DOTween, LoopType, Tweener


class _CharacterTween(Tweener):
    def __init__(self, animator, channel, selection, to, duration):
        self._animator, self._channel, self._selection = animator, channel, selection
        super().__init__(lambda: animator._views[channel][selection].copy(), self._write, to, duration)

    def _write(self, value):
        animator = self._animator
        animator._views[self._channel][self._selection] = value
        manager = self._owner
        parent = self._parent
        while parent is not None:
            manager, parent = parent._owner, parent._parent
        if manager is None:
            animator.Apply()
        else:
            manager._defer_commit(animator.Apply)

    def _initialize(self):
        if self._start is not None:
            return
        start = self._getter()
        end = np.broadcast_to(np.asarray(self._end, dtype=start.dtype), start.shape).copy()
        if self._relative:
            end += start
        if self._from:
            start, end = end, start
        self._start, self._end, self._delta = start, end, end-start
        if self._speed_based:
            distance = np.abs(self._delta) if self._channel in ("rotations", "skews", "alphas") else np.linalg.norm(self._delta, axis=-1)
            distance = np.max(distance, initial=0)
            self.duration = float(distance)/self.duration

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        factor = self._ease(progress)+(cycle if self.loop_type == LoopType.Incremental else 0)
        value = self._start+self._delta*factor
        if self._snapping:
            value = np.rint(value)
        if self._channel not in ("rotations", "skews", "alphas") and (self._constraint or self._alpha_only):
            axes = np.arange(value.shape[-1])
            mask = axes == 3 if self._alpha_only else (self._constraint & (1 << axes)) != 0
            value = np.where(mask, value, self._getter())
        self._setter(value)


class TextTweenSelection:
    def __init__(self, animator, selection):
        self.animator, self.selection = animator, selection

    def _tween(self, channel, to, duration):
        tween = DOTween.add(_CharacterTween(self.animator, channel, self.selection, to, duration))
        self.animator._tweens.add(tween)
        return tween.SetTarget(self.animator.text)

    def DOOffset(self, to, duration): return self._tween("offsets", to, duration)
    def DORotate(self, to, duration): return self._tween("rotations", to, duration)
    def DOScale(self, to, duration): return self._tween("scales", to, duration)
    def DOSkew(self, to, duration): return self._tween("skews", to, duration)
    def DOColor(self, to, duration): return self._tween("colors", to, duration)
    def DOFade(self, to, duration): return self._tween("alphas", to, duration)
    def DOVertices(self, to, duration): return self._tween("vertex_offsets", to, duration)


class DOTweenTextAnimator:
    def __init__(self, text):
        self.text = text
        self._tweens = WeakSet()
        self._disposed = False
        self.Refresh()

    def Refresh(self):
        for tween in tuple(self._tweens):
            tween.Kill()
        self.layout = self.text.get_text_layout()
        self.buffer = self.text.create_character_buffer()
        self._views = {name: getattr(self.buffer, name) for name in
                       ("offsets", "rotations", "scales", "skews", "colors", "vertex_offsets")}
        self._views["alphas"] = self.buffer.colors[:, :, 3]
        self._disposed = False
        self.text.reset_character_data(TextGeometryLayer.Manual)
        return self

    def Range(self, start=0, count=None):
        if self.text.get_text_layout() is not self.layout:
            self.Refresh()
        end = self.buffer.character_count if count is None else start+count
        if not 0 <= start <= end <= self.buffer.character_count:
            raise ValueError("Character range exceeds the native layout")
        return TextTweenSelection(self, slice(start, end))

    def Character(self, index): return self.Range(index, 1)

    def Word(self, index):
        if self.text.get_text_layout() is not self.layout:
            self.Refresh()
        word = self.layout.words[index]
        return self.Range(word.character_start, word.character_end-word.character_start)

    def Line(self, index):
        if self.text.get_text_layout() is not self.layout:
            self.Refresh()
        if not 0 <= index < len(self.layout.lines):
            raise IndexError(index)
        indices = np.array([i for i, char in enumerate(self.layout.characters) if char.line == index], dtype=np.intp)
        return TextTweenSelection(self, indices)

    def Apply(self):
        if self._disposed:
            return self
        if self.text.get_text_layout() is not self.layout:
            return self.Refresh()
        self.text.set_character_data(self.buffer, TextGeometryLayer.Manual)
        return self

    def Reset(self):
        for tween in tuple(self._tweens):
            tween.Kill()
        self.buffer.reset()
        self.text.reset_character_data(TextGeometryLayer.Manual)
        return self

    def Dispose(self):
        self.Reset()
        self._disposed = True

    def _get(self, channel, index):
        selection = self.Character(index).selection
        return self._views[channel][selection][0].copy()

    def _set(self, channel, index, value):
        selection = self.Character(index).selection
        self._views[channel][selection] = value
        return self.Apply()

    def GetCharOffset(self, index): return self._get("offsets", index)
    def GetCharRotation(self, index): return float(self._get("rotations", index))
    def GetCharScale(self, index): return self._get("scales", index)
    def GetCharColor(self, index): return self._get("colors", index)[0]
    def SetCharOffset(self, index, value): return self._set("offsets", index, value)
    def SetCharRotation(self, index, value): return self._set("rotations", index, value)
    def SetCharScale(self, index, value): return self._set("scales", index, value)
    def SetCharColor(self, index, value): return self._set("colors", index, value)
    def SetCharAlpha(self, index, value): return self._set("alphas", index, value)
    def DOOffsetChar(self, index, to, duration): return self.Character(index).DOOffset(to, duration)
    def DORotateChar(self, index, to, duration): return self.Character(index).DORotate(to, duration)
    def DOScaleChar(self, index, to, duration): return self.Character(index).DOScale(to, duration)
    def DOColorChar(self, index, to, duration): return self.Character(index).DOColor(to, duration)
    def DOFadeChar(self, index, to, duration): return self.Character(index).DOFade(to, duration)
