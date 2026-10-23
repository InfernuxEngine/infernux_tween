"""Character tweens share the native Manual layer and the standard tween clock."""
from enum import Enum
from typing import overload
from weakref import WeakSet, WeakValueDictionary

import numpy as np
from infernux.ui import UIText
from infernux.lib import TextGeometryLayer, Vector3, quatf

from .core import _default_manager, _ColorTweener, _FloatTweener, _VectorTweener, Tweener, _UNSET
from .motion import _punch_tween, _shake_tween
from .rotation import EulerTweener, RotateMode


class SkewSpanMode(Enum):
    DEFAULT = "Default"
    AS_MAX_SKEW_FACTOR = "AsMaxSkewFactor"


_UI_AXES = np.array((1, -1, 1), dtype=np.float32)


def _vector(value, scalar=False):
    if isinstance(value, Vector3):
        return value
    if scalar and type(value) in (int, float):
        return Vector3(value, value, value)
    raise TypeError("Expected Vector3" + (" or float" if scalar else ""))


def _array(value):
    return np.asarray(tuple(value) if isinstance(value, Vector3) else value, dtype=np.float32)


def _rotation_matrices(eulers):
    sx, sy, sz = np.sin(np.deg2rad(eulers)).T
    cx, cy, cz = np.cos(np.deg2rad(eulers)).T
    return np.stack((cy*cz+sy*sx*sz, -cy*sz+sy*sx*cz, sy*cx,
                     cx*sz, cx*cz, -sx,
                     -sy*cz+cy*sx*sz, sy*sz+cy*sx*cz, cy*cx), axis=-1).reshape(-1, 3, 3)


class _CharacterTween(Tweener):
    def __init__(self, animator, channel, selection, to, duration):
        self._animator, self._channel, self._selection = animator, channel, selection
        def read():
            if channel in ("colors", "alphas"):
                colors = animator._read_colors(selection)
                return colors if channel == "colors" else colors[..., 3]
            return animator._views[channel][selection].copy()
        super().__init__(read, self._write, _array(to), duration)

    def _write(self, value):
        self._animator._write(self._channel, self._selection, value, self, 2 if self._alpha_only else None)

    def _relative_value(self, current, value):
        if self._alpha_only:
            result = current.copy()
            result[..., 3] += value[..., 3]
            return result
        return current + _array(value)

    def _capture_values(self):
        current = self._getter()
        start = current if self._manual_start is _UNSET else _array(self._manual_start)
        end = self._end
        if self._from:
            if self._channel == "colors" and type(self._from_value) in (int, float):
                self._alpha_only = True
                value = current.copy()
                value[..., 3] = self._from_value
            else:
                value = self._from_value
            if value is _UNSET:
                start, end = end, start
            else:
                start = value
            start = np.broadcast_to(_array(start), current.shape).copy()
            end = np.broadcast_to(_array(end), current.shape).copy()
            if self._relative:
                start = self._relative_value(current, start)
                if value is not _UNSET:
                    end = self._relative_value(current, end)
            if self._constraint or self._alpha_only:
                axes = np.arange(current.shape[-1])
                mask = axes == 3 if self._alpha_only else (self._constraint & (1 << axes)) != 0
                start = np.where(mask, start, current)
        return start, end

    def _set_values(self, start, end):
        shape = self._animator._views[self._channel][self._selection].shape
        start, end = (np.broadcast_to(_array(value), shape).copy() for value in (start, end))
        self._start, self._end, self._delta = start, end, end-start

    def _distance(self):
        delta = self._delta
        if self._alpha_only:
            distance = np.abs(delta[..., 3])
        elif self._channel in ("skews", "alphas"):
            distance = np.abs(delta)
        else:
            if self._constraint:
                delta = delta[..., (self._constraint & (1 << np.arange(delta.shape[-1]))) != 0]
            distance = np.linalg.norm(delta, axis=-1)
        return float(np.max(distance, initial=0))

    def _snap(self, value):
        value = _array(value)
        if not self._constraint:
            return np.rint(value)
        mask = (self._constraint & (1 << np.arange(value.shape[-1]))) != 0
        return np.where(mask, np.rint(value), value)

    def set_options(self, *args, **kwargs):
        option_type = (_ColorTweener if self._channel == "colors" else
                       _FloatTweener if self._channel in ("skews", "alphas") else _VectorTweener)
        return option_type.set_options(self, *args, **kwargs)

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        value = self._start+self._delta*(self._ease(progress)+self._incremental_cycles(cycle))
        if self._snapping:
            value = np.rint(value)
        if self._channel not in ("skews", "alphas") and (self._constraint or self._alpha_only):
            axes = np.arange(value.shape[-1])
            mask = axes == 3 if self._alpha_only else (self._constraint & (1 << axes)) != 0
            value = np.where(mask, value, self._getter())
        self._setter(value)


class TextTweenSelection:
    """Additional batch API over native logical grapheme indices."""
    def __init__(self, animator, selection):
        self.animator, self.selection = animator, selection

    def _tween(self, channel, to, duration):
        return self.animator._track(_CharacterTween(self.animator, channel, self.selection, to, duration))

    def do_offset(self, to, duration): return self._tween("offsets", to, duration)
    def do_rotate(self, to, duration): return self._tween("rotations", to, duration)
    def do_scale(self, to, duration): return self._tween("scales", to, duration)
    def do_skew(self, to, duration): return self._tween("skews", to, duration)
    def do_color(self, to, duration): return self._tween("colors", to, duration)
    def do_fade(self, to, duration): return self._tween("alphas", to, duration)
    def do_vertices(self, to, duration): return self._tween("vertex_offsets", to, duration)


class TextTweenAnimator:
    _instances = WeakValueDictionary()

    def __init__(self, target: UIText):
        self.text = target
        self._tweens = WeakSet()
        self._disposed = False
        self.refresh()
        previous = self._instances.get(id(target))
        self._instances[id(target)] = self
        if previous is not None:
            previous.dispose()

    @staticmethod
    def dispose_instance_for(target: UIText) -> None:
        animator = TextTweenAnimator._instances.get(id(target))
        if animator is not None:
            animator.dispose()

    def _kill_tweens(self):
        for tween in tuple(self._tweens):
            tween.kill()

    def refresh(self) -> None:
        if self._disposed:
            raise RuntimeError("TextTweenAnimator has been disposed")
        self._kill_tweens()
        if self._disposed:
            return
        self.layout = self.text.get_text_layout()
        self.buffer = self.text.create_character_buffer()
        count = self.buffer.character_count
        self._views = {name: np.zeros((count, 3), dtype=np.float32) for name in ("offsets", "rotations")}
        glyphs = self.layout.glyphs
        self._glyph_colors = np.array([glyphs[char.glyph_start].color if char.glyph_start < char.glyph_end else (1, 1, 1, 1)
                                       for char in self.layout.characters], dtype=np.float32).reshape(count, 4)
        colors = np.repeat((self._glyph_colors*_array(self.text.color))[:, None, :], 4, axis=1)
        self._views.update(scales=np.ones((count, 3), dtype=np.float32),
                           vertex_offsets=np.zeros((count, 4, 3), dtype=np.float32),
                           skews=self.buffer.skews, colors=colors, alphas=colors[:, :, 3])
        self._dirty_transforms = np.zeros(count, dtype=bool)
        self._bounds = np.asarray([char.bounds for char in self.layout.characters], dtype=np.float32).reshape(count, 4)
        self._visible = np.array([any(glyph.visible for glyph in glyphs[char.glyph_start:char.glyph_end])
                                  for char in self.layout.characters], dtype=bool)
        self._disposed = False
        self.text.reset_character_data(TextGeometryLayer.Manual)

    def _check_layout(self):
        if not self._disposed and self.text.get_text_layout() is not self.layout:
            self.refresh()

    def range(self, start=0, count=None):
        self._check_layout()
        end = self.buffer.character_count if count is None else start+count
        if self._disposed or not 0 <= start <= end <= self.buffer.character_count:
            raise ValueError("Character range exceeds the native layout")
        return TextTweenSelection(self, slice(start, end))

    def character(self, index): return self.range(index, 1)

    def word(self, index):
        self._check_layout()
        word = self.layout.words[index]
        return self.range(word.character_start, word.character_end-word.character_start)

    def line(self, index):
        self._check_layout()
        if not 0 <= index < len(self.layout.lines):
            raise IndexError(index)
        indices = np.array([i for i, char in enumerate(self.layout.characters) if char.line == index], dtype=np.intp)
        return TextTweenSelection(self, indices)

    def _valid(self, char_index):
        if type(char_index) is not int:
            raise TypeError("char_index must be int")
        self._check_layout()
        return not self._disposed and 0 <= char_index < self.buffer.character_count and self._visible[char_index]

    def _write(self, channel, selection, value, tween=None, color_mode=None):
        if self._disposed:
            return
        self._views[channel][selection] = value
        if channel in ("offsets", "rotations", "scales"):
            self._dirty_transforms[selection] = True
        elif channel == "vertex_offsets":
            vertices = self._views[channel][selection]*_UI_AXES
            self.buffer.vertex_offsets[selection] = vertices[..., :2]
            self.buffer.vertex_depth_offsets[selection] = vertices[..., 2]
        elif channel in ("colors", "alphas"):
            self.buffer.colors[selection] = self._views["colors"][selection]
            mode = color_mode if color_mode is not None else (3 if channel == "colors" else 2)
            self.buffer.color_overrides[selection] = self.buffer.color_overrides[selection].astype(np.uint8) | mode
        manager = _default_manager
        if tween is not None:
            while tween._parent is not None:
                tween = tween._parent
            manager = tween._owner or manager
        manager._defer_commit(self.apply)

    def _track(self, tween):
        self._tweens.add(tween)
        return _default_manager.add(tween).set_target(self.text)

    def _char_tween(self, char_index, channel, factory, color_mode=None):
        if not self._valid(char_index):
            return None
        def read():
            value = self._views[channel][char_index]
            return self._read_color(char_index) if channel == "colors" else Vector3(*value)
        def write(value):
            self._write(channel, char_index, tuple(value) if isinstance(value, Vector3) else value, tween, color_mode)
        tween = factory(read, write)
        return self._track(tween)

    def apply(self):
        if self._disposed:
            return self
        if self.text.get_text_layout() is not self.layout:
            self.refresh()
            return self
        indices = np.flatnonzero(self._dirty_transforms)
        if indices.size:
            linear = _rotation_matrices(self._views["rotations"][indices])*self._views["scales"][indices, None, :]
            self.buffer.affine_transforms[indices, :, :3] = linear*_UI_AXES[:, None]*_UI_AXES[None, :]
            self.buffer.affine_transforms[indices, :, 3] = self._views["offsets"][indices]*_UI_AXES
            self._dirty_transforms[indices] = False
        self.text.set_character_data(self.buffer, TextGeometryLayer.Manual)
        return self

    def reset(self) -> None:
        if self._disposed:
            return
        self._kill_tweens()
        if self._disposed:
            return
        for channel in ("offsets", "rotations", "vertex_offsets"):
            self._views[channel].fill(0)
        self._views["scales"].fill(1)
        self._views["colors"][:] = self._glyph_colors[:, None, :]*_array(self.text.color)
        self._dirty_transforms.fill(False)
        self.buffer.reset()
        self.text.reset_character_data(TextGeometryLayer.Manual)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        key = id(self.text)
        owned = self._instances.get(key) is self
        if owned:
            self._instances.pop(key)
        self._kill_tweens()
        if owned and key not in self._instances:
            self.text.reset_character_data(TextGeometryLayer.Manual)

    def _get_vector(self, channel, char_index):
        return Vector3(*self._views[channel][char_index]) if self._valid(char_index) else Vector3(0, 0, 0)

    def _set_vector(self, channel, char_index, value):
        if self._valid(char_index):
            self._write(channel, char_index, tuple(_vector(value)))

    def get_char_offset(self, char_index: int) -> Vector3: return self._get_vector("offsets", char_index)
    def get_char_rotation(self, char_index: int) -> Vector3:
        return quatf.euler(*self._get_vector("rotations", char_index)).euler_angles
    def get_char_scale(self, char_index: int) -> Vector3: return self._get_vector("scales", char_index)
    def _read_colors(self, selection):
        colors = self._views["colors"][selection].copy()
        base = self._glyph_colors[selection]*_array(self.text.color)
        flags = self.buffer.color_overrides[selection].astype(np.uint8)
        colors[..., :3] = np.where((flags & 1)[..., None, None], colors[..., :3], base[..., None, :3])
        colors[..., 3] = np.where((flags & 2)[..., None], colors[..., 3], base[..., 3, None])
        return colors

    def _read_color(self, char_index):
        return self._read_colors(char_index)[0].tolist()

    def get_char_color(self, char_index: int) -> list[float]:
        return self._read_color(char_index) if self._valid(char_index) else [1.0]*4
    def set_char_offset(self, char_index: int, offset: Vector3) -> None: self._set_vector("offsets", char_index, offset)
    def set_char_rotation(self, char_index: int, rotation: Vector3) -> None: self._set_vector("rotations", char_index, rotation)
    def set_char_scale(self, char_index: int, scale: Vector3) -> None: self._set_vector("scales", char_index, scale)
    def set_char_color(self, char_index: int, color: list[float]) -> None:
        if self._valid(char_index):
            self._write("colors", char_index, color)

    def do_offset_char(self, char_index: int, end_value: Vector3, duration: float):
        return self._char_tween(char_index, "offsets", lambda read, write: _VectorTweener(read, write, _vector(end_value), duration))

    def do_rotate_char(self, char_index: int, end_value: Vector3, duration: float, mode: RotateMode=RotateMode.FAST):
        return self._char_tween(char_index, "rotations", lambda read, write: EulerTweener(
            lambda: quatf.euler(*read()), lambda value: write(value.euler_angles), _vector(end_value), duration, mode))

    @overload
    def do_scale_char(self, char_index: int, end_value: float, duration: float): ...
    @overload
    def do_scale_char(self, char_index: int, end_value: Vector3, duration: float): ...
    def do_scale_char(self, char_index, end_value, duration):
        return self._char_tween(char_index, "scales", lambda read, write: _VectorTweener(read, write, _vector(end_value, True), duration))

    def do_color_char(self, char_index: int, end_value: list[float], duration: float):
        return self._char_tween(char_index, "colors", lambda read, write: _ColorTweener(read, write, end_value, duration))

    def do_fade_char(self, char_index: int, end_value: float, duration: float):
        return self._char_tween(char_index, "colors", lambda read, write:
                                _ColorTweener(read, write, [0, 0, 0, end_value], duration).set_options(True), 2)

    def _punch(self, char_index, channel, punch, duration, vibrato, elasticity, scalar=False):
        if duration <= 0:
            return None
        return self._char_tween(char_index, channel, lambda read, write:
                                _punch_tween(read, write, _vector(punch, scalar), duration, vibrato, elasticity))

    def do_punch_char_offset(self, char_index: int, punch: Vector3, duration: float, vibrato: int=10, elasticity: float=1):
        return self._punch(char_index, "offsets", punch, duration, vibrato, elasticity)

    def do_punch_char_rotation(self, char_index: int, punch: Vector3, duration: float, vibrato: int=10, elasticity: float=1):
        return self._punch(char_index, "rotations", punch, duration, vibrato, elasticity)

    @overload
    def do_punch_char_scale(self, char_index: int, punch: float, duration: float, vibrato: int=10, elasticity: float=1): ...
    @overload
    def do_punch_char_scale(self, char_index: int, punch: Vector3, duration: float, vibrato: int=10, elasticity: float=1): ...
    def do_punch_char_scale(self, char_index, punch, duration, vibrato=10, elasticity=1):
        return self._punch(char_index, "scales", punch, duration, vibrato, elasticity, True)

    def _shake(self, char_index, channel, duration, strength, vibrato, randomness, fade_out, scalar):
        if duration <= 0:
            return None
        return self._char_tween(char_index, channel, lambda read, write:
                                _shake_tween(read, write, duration, _vector(strength, scalar), vibrato, randomness, fade_out))

    @overload
    def do_shake_char_offset(self, char_index: int, duration: float, strength: float, vibrato: int=10, randomness: float=90, fade_out: bool=True): ...
    @overload
    def do_shake_char_offset(self, char_index: int, duration: float, strength: Vector3, vibrato: int=10, randomness: float=90, fade_out: bool=True): ...
    def do_shake_char_offset(self, char_index, duration, strength, vibrato=10, randomness=90, fade_out=True):
        return self._shake(char_index, "offsets", duration, strength, vibrato, randomness, fade_out, True)

    def do_shake_char_rotation(self, char_index: int, duration: float, strength: Vector3, vibrato: int=10, randomness: float=90, fade_out: bool=True):
        return self._shake(char_index, "rotations", duration, strength, vibrato, randomness, fade_out, False)

    @overload
    def do_shake_char_scale(self, char_index: int, duration: float, strength: float, vibrato: int=10, randomness: float=90, fade_out: bool=True): ...
    @overload
    def do_shake_char_scale(self, char_index: int, duration: float, strength: Vector3, vibrato: int=10, randomness: float=90, fade_out: bool=True): ...
    def do_shake_char_scale(self, char_index, duration, strength, vibrato=10, randomness=90, fade_out=True):
        return self._shake(char_index, "scales", duration, strength, vibrato, randomness, fade_out, True)

    def shift_char_vertices(self, char_index: int, top_left_shift: Vector3, top_right_shift: Vector3,
                            bottom_left_shift: Vector3, bottom_right_shift: Vector3) -> None:
        if self._valid(char_index):
            shift = np.array([tuple(_vector(value)) for value in
                              (top_left_shift, top_right_shift, bottom_right_shift, bottom_left_shift)], dtype=np.float32)
            self._write("vertex_offsets", char_index, self._views["vertex_offsets"][char_index]+shift)

    def reset_vertices_shift(self, char_index: int) -> None:
        if self._valid(char_index):
            self._write("vertex_offsets", char_index, 0)

    def skew_char_x(self, char_index: int, skew_factor: float, skew_top: bool=True) -> float:
        if not self._valid(char_index):
            return 0.0
        corners = self._views["vertex_offsets"][char_index].copy()
        corners[[0, 1] if skew_top else [2, 3], 0] += skew_factor
        self._write("vertex_offsets", char_index, corners)
        return float(skew_factor)

    def skew_char_y(self, char_index: int, skew_factor: float, skew_right: bool=True, fixed_skew: bool=False) -> float:
        if not self._valid(char_index):
            return 0.0
        left, top, right, bottom = self._bounds[char_index]
        amount = skew_factor if fixed_skew else skew_factor*abs((right-left)/(bottom-top))
        corners = self._views["vertex_offsets"][char_index].copy()
        corners[[1, 2] if skew_right else [0, 3], 1] += amount
        self._write("vertex_offsets", char_index, corners)
        return float(amount)

    def _span(self, from_char_index, to_char_index):
        self._check_layout()
        indices = np.arange(max(0, from_char_index), min(to_char_index+1, self.buffer.character_count), dtype=np.intp)
        return indices[self._visible[indices]] if not self._disposed else indices[:0]

    def _corner_positions(self, indices):
        bounds = self._bounds[indices]
        corners = np.zeros((len(indices), 4, 3), dtype=np.float32)
        corners[:, :, 0] = bounds[:, [0, 2, 2, 0]]
        corners[:, :, 1] = -bounds[:, [1, 1, 3, 3]]
        centers = (corners[:, :1]+corners[:, 2:3])*0.5
        scaled = (corners-centers)*self._views["scales"][indices, None, :]
        return (np.einsum("nij,nkj->nki", _rotation_matrices(self._views["rotations"][indices]), scaled)
                +centers+self._views["offsets"][indices, None, :]+self._views["vertex_offsets"][indices])

    def skew_span_x(self, from_char_index: int, to_char_index: int, skew_factor: float, skew_top: bool=True) -> None:
        indices = self._span(from_char_index, to_char_index)
        if indices.size:
            corners = self._views["vertex_offsets"][indices].copy()
            corners[:, [0, 1] if skew_top else [2, 3], 0] += skew_factor
            self._write("vertex_offsets", indices, corners)

    def skew_span_y(self, from_char_index: int, to_char_index: int, skew_factor: float,
                    mode: SkewSpanMode=SkewSpanMode.DEFAULT, skew_right: bool=True) -> None:
        if not isinstance(mode, SkewSpanMode):
            raise TypeError("mode must be SkewSpanMode")
        indices = self._span(from_char_index, to_char_index)
        if not indices.size:
            return
        bounds = self._bounds[indices]
        vertices = self._corner_positions(indices)
        if mode == SkewSpanMode.AS_MAX_SKEW_FACTOR:
            skew_factor *= abs((vertices[-1, 1, 1]-vertices[-1, 2, 1])/(vertices[-1, 2, 0]-vertices[0, 3, 0]))
        if not skew_right:
            indices, bounds, vertices = indices[::-1], bounds[::-1], vertices[::-1]
        amounts = skew_factor*np.abs((bounds[:, 2]-bounds[:, 0])/(bounds[:, 3]-bounds[:, 1]))
        widths = np.abs(vertices[:, 2, 0]-vertices[:, 3, 0])
        gaps = (np.abs(vertices[1:, 3, 0]-vertices[:-1, 2, 0]) if skew_right else
                np.abs(vertices[1:, 2, 0]-vertices[:-1, 3, 0]))
        self._views["offsets"][indices[1:], 0] = self._views["offsets"][indices[1:], 2] = 0
        self._views["offsets"][indices, 1] += np.r_[0, np.cumsum(amounts[:-1]*(1+gaps/widths[:-1]))]
        self._dirty_transforms[indices] = True
        corners = self._views["vertex_offsets"][indices].copy()
        corners[:, [1, 2] if skew_right else [0, 3], 1] += amounts[:, None]
        self._write("vertex_offsets", indices, corners)
