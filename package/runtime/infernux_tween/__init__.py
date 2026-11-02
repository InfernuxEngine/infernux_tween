"""Tween and sequence playback for Infernux."""
from math import isfinite

from .core import (
    AutoPlay, AxisConstraint, LogBehaviour, RewindCallbackMode, SafeModeLogBehaviour, NestedTweenFailureBehaviour, LoopType, OnEnableBehaviour, OnDisableBehaviour,
    Sequence, Tween, Tweener, TweenManager, TweenParams, UpdateType, VisualManagerPreset, _default_manager,
)
from .curve import EaseCurve, CubicBezier, TweenCurve
from .rect import switch_to_rect_transform, RectOffsetPlugin
from .ease import Bounce, Ease, EaseFactory, EaseManager, Flash, stop_motion
from .link import LinkBehaviour
from .motion import ShakeRandomnessMode, SpiralMode
from .path import HandlesDrawMode, HandlesType, OrientType, Path, PathMode, PathType, PathTween, PathOptions, PathPlugin, ControlPoint, ControlPointArray, Float32Array, TweenInspectorMode
from .plugin import AbsTweenPlugin, NoOptions, TweenerCore, UpdateNotice
from ._builtin_plugins import FloatOptions, VectorOptions, ColorOptions, UintOptions, RectOptions, Vector3ArrayOptions
from ._builtin_plugins import (FloatPlugin, DoublePlugin, IntPlugin, LongPlugin, UintPlugin, UlongPlugin,
    Vector2Plugin, Vector3Plugin, Vector4Plugin, ColorPlugin, RectPlugin, StringPlugin, QuaternionPlugin, Vector3ArrayPlugin)
from .array import Vector3Array
from .spiral import SpiralOptions, SpiralPlugin
from .rotation import RotateMode, PureQuaternionPlugin, QuaternionOptions
from .circle import CircleOptions, CirclePlugin, TweenUtils
from .spring import Spring
from .string import ScrambleMode, StringOptions
from .text import SkewSpanMode, TextTweenAnimator
from .virtual import delayed_call, eased_value
from .shortcuts import Color2, CultureInfo
from .yield_instruction import (
    TweenYieldInstruction, WaitForCompletion, WaitForKill, WaitForStart,
    WaitForRewind, WaitForElapsedLoops, WaitForPosition,
)
from .editor_preview import TweenEditorPreview
from .settings import SafeModeOptions, TweenSettings

version = "0.3.1"
from .shortcuts import (
    twn_path,
    twn_local_path,
    twn_rotate_quaternion,
    twn_local_rotate_quaternion,
    twn_blendable_local_move_by,
    twn_blendable_move_by,
    twn_blendable_scale_by,
    twn_blendable_rotate_by,
    twn_blendable_local_rotate_by,
    twn_spiral,
    twn_jump,
    twn_local_jump,
    twn_punch_position,
    twn_punch_rotation,
    twn_punch_scale,
    twn_shake_position,
    twn_shake_rotation,
    twn_shake_scale,
    twn_offset,
    twn_tiling,
    twn_aspect,
    twn_rect,
    twn_pixel_rect,
    twn_move,
    twn_local_move,
    twn_scale,
    twn_rotate,
    twn_local_rotate,
    twn_look_at,
    twn_dynamic_look_at,
    twn_color,
    twn_blendable_color,
    twn_fade,
    twn_gradient_color,
    twn_value,
    twn_normalized_pos,
    twn_horizontal_normalized_pos,
    twn_vertical_normalized_pos,
    twn_set_float,
    twn_size_delta,
    twn_anchor_min,
    twn_anchor_max,
    twn_anchor_pos,
    twn_anchor_pos_x,
    twn_anchor_pos_y,
    twn_anchor_pos3d,
    twn_anchor_pos3d_x,
    twn_anchor_pos3d_y,
    twn_anchor_pos3d_z,
    twn_jump_anchor_pos,
    twn_punch_anchor_pos,
    twn_shake_anchor_pos,
    twn_shape_circle,
    twn_pivot,
    twn_pivot_x,
    twn_pivot_y,
    twn_min_size,
    twn_preferred_size,
    twn_flexible_size,
    twn_fill_amount,
    twn_text,
    twn_counter,
    twn_max_visible_characters,
    twn_move_x,
    twn_move_y,
    twn_move_z,
    twn_local_move_x,
    twn_local_move_y,
    twn_local_move_z,
    twn_scale_x,
    twn_scale_y,
    twn_scale_z,
    twn_pitch,
    twn_intensity,
    twn_shadow_strength,
    twn_field_of_view,
    twn_ortho_size,
    twn_near_clip_plane,
    twn_far_clip_plane,
    twn_font_size,
    twn_time_scale,
    twn_resize,
    twn_time,
    twn_float,
    twn_vector,
    twn_complete,
    twn_kill,
    twn_flip,
    twn_goto,
    twn_pause,
    twn_play,
    twn_play_backwards,
    twn_play_forward,
    twn_restart,
    twn_rewind,
    twn_smooth_rewind,
    twn_toggle_pause,
)
from .motion import twn_blendable_punch_rotation

init = _default_manager.init
set_tweens_capacity = _default_manager.set_tweens_capacity
clear_cached_tweens = _default_manager.clear_cached_tweens
validate = _default_manager.validate
total_pooled_tweens = _default_manager.total_pooled_tweens

add = _default_manager.add
to = _default_manager.to
to_axis = _default_manager.to_axis
to_alpha = _default_manager.to_alpha
to_array = _default_manager.to_array
punch = _default_manager.punch
shake = _default_manager.shake
sequence = _default_manager.sequence
update = _default_manager.update
manual_update = _default_manager.manual_update
play_all = _default_manager.play_all
play = _default_manager.play
play_forward_all = _default_manager.play_forward_all
play_forward = _default_manager.play_forward
play_backwards_all = _default_manager.play_backwards_all
play_backwards = _default_manager.play_backwards
pause_all = _default_manager.pause_all
pause = _default_manager.pause
flip_all = _default_manager.flip_all
flip = _default_manager.flip
restart_all = _default_manager.restart_all
restart = _default_manager.restart
rewind_all = _default_manager.rewind_all
rewind = _default_manager.rewind
smooth_rewind_all = _default_manager.smooth_rewind_all
smooth_rewind = _default_manager.smooth_rewind
toggle_pause_all = _default_manager.toggle_pause_all
toggle_pause = _default_manager.toggle_pause
complete_all = _default_manager.complete_all
complete = _default_manager.complete
kill_all = _default_manager.kill_all
kill = _default_manager.kill
goto_all = _default_manager.goto_all
goto = _default_manager.goto
is_tweening = _default_manager.is_tweening
tweens_by_id = _default_manager.tweens_by_id
tweens_by_target = _default_manager.tweens_by_target
playing_tweens = _default_manager.playing_tweens
paused_tweens = _default_manager.paused_tweens
total_active_tweens = _default_manager.total_active_tweens
total_active_tweeners = _default_manager.total_active_tweeners
total_active_sequences = _default_manager.total_active_sequences
total_tweens_by_id = _default_manager.total_tweens_by_id
total_playing_tweens = _default_manager.total_playing_tweens
get_diagnostics = _default_manager.get_diagnostics
get_editor_report = _default_manager.get_editor_report
clear = _default_manager.clear


def get_time_scale() -> float:
    return _default_manager.time_scale


def set_time_scale(value: float) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError("time_scale must be finite and nonnegative")
    _default_manager.time_scale = value


__all__ = [
    'SafeModeOptions', 'TweenSettings',
    'RewindCallbackMode',
    'TweenEditorPreview',
    'TweenYieldInstruction', 'WaitForCompletion', 'WaitForKill', 'WaitForStart',
    'WaitForRewind', 'WaitForElapsedLoops', 'WaitForPosition',
    'version', 'instance',
    'switch_to_rect_transform',
    'get_editor_report',
    'twn_normalized_pos', 'twn_horizontal_normalized_pos', 'twn_vertical_normalized_pos', 'twn_set_float',
    'AbsTweenPlugin', 'NoOptions', 'TweenerCore', 'PureQuaternionPlugin', 'CircleOptions', 'CirclePlugin', 'UpdateNotice', 'EaseManager',
    'FloatOptions', 'VectorOptions', 'ColorOptions', 'UintOptions', 'RectOptions', 'StringOptions', 'Vector3ArrayOptions', 'Vector3Array', 'QuaternionOptions',
    'FloatPlugin', 'DoublePlugin', 'IntPlugin', 'LongPlugin', 'UintPlugin', 'UlongPlugin',
    'Vector2Plugin', 'Vector3Plugin', 'Vector4Plugin', 'ColorPlugin', 'RectPlugin', 'StringPlugin', 'QuaternionPlugin', 'Vector3ArrayPlugin',
    'RectOffsetPlugin',
    'NestedTweenFailureBehaviour', 'LogBehaviour', 'SafeModeLogBehaviour', 'init', 'set_tweens_capacity', 'clear_cached_tweens', 'validate', 'total_pooled_tweens',
    'SkewSpanMode', 'twn_blendable_punch_rotation', 'AutoPlay', 'AxisConstraint', 'Ease', 'EaseCurve',
    'OnEnableBehaviour', 'OnDisableBehaviour', 'VisualManagerPreset',
    'virtual', 'delayed_call', 'eased_value', 'stop_motion',
    'EaseFactory', 'CubicBezier', 'TweenCurve', 'Bounce', 'Flash', 'TweenUtils',
    'LinkBehaviour', 'LoopType', 'OrientType', 'Path', 'PathMode', 'PathType', 'PathTween', 'PathOptions', 'PathPlugin',
    'ControlPoint', 'ControlPointArray', 'Float32Array', 'RotateMode',
    'HandlesDrawMode', 'HandlesType', 'TweenInspectorMode',
    'ScrambleMode', 'Sequence', 'ShakeRandomnessMode', 'SpiralMode', 'SpiralOptions', 'SpiralPlugin', 'Spring', 'TextTweenAnimator',
    'Tween', 'Tweener', 'TweenManager', 'TweenParams', 'Color2', 'CultureInfo', 'UpdateType', 'add',
    'to', 'to_axis', 'to_alpha', 'to_array', 'punch', 'shake', 'sequence', 'update', 'manual_update',
    'play_all', 'play', 'play_forward_all', 'play_forward', 'play_backwards_all', 'play_backwards',
    'pause_all', 'pause', 'flip_all', 'flip', 'restart_all', 'restart', 'rewind_all', 'rewind',
    'smooth_rewind_all', 'smooth_rewind', 'toggle_pause_all', 'toggle_pause', 'complete_all',
    'complete', 'kill_all', 'kill',
    'goto_all', 'goto', 'is_tweening', 'tweens_by_id', 'tweens_by_target', 'playing_tweens',
    'paused_tweens', 'total_active_tweens', 'total_active_tweeners', 'total_active_sequences',
    'total_tweens_by_id', 'total_playing_tweens', 'get_diagnostics', 'clear', 'twn_path',
    'twn_local_path', 'twn_rotate_quaternion', 'twn_local_rotate_quaternion', 'twn_blendable_local_move_by',
    'twn_blendable_move_by', 'twn_blendable_scale_by', 'twn_blendable_rotate_by',
    'twn_blendable_local_rotate_by', 'twn_spiral', 'twn_jump', 'twn_local_jump', 'twn_punch_position',
    'twn_punch_rotation', 'twn_punch_scale', 'twn_shake_position', 'twn_shake_rotation', 'twn_shake_scale',
    'twn_offset', 'twn_tiling', 'twn_aspect', 'twn_rect', 'twn_pixel_rect', 'twn_move', 'twn_local_move', 'twn_scale', 'twn_rotate', 'twn_local_rotate', 'twn_look_at',
    'twn_dynamic_look_at', 'twn_color', 'twn_blendable_color', 'twn_fade', 'twn_gradient_color', 'twn_value',
    'twn_size_delta', 'twn_min_size', 'twn_preferred_size', 'twn_flexible_size', 'twn_fill_amount', 'twn_text', 'twn_counter', 'twn_max_visible_characters', 'twn_move_x', 'twn_move_y',
    'twn_move_z', 'twn_local_move_x', 'twn_local_move_y', 'twn_local_move_z', 'twn_scale_x', 'twn_scale_y',
    'twn_scale_z', 'twn_pitch', 'twn_intensity', 'twn_shadow_strength', 'twn_field_of_view', 'twn_ortho_size',
    'twn_near_clip_plane', 'twn_far_clip_plane', 'twn_font_size', 'twn_time_scale', 'twn_resize', 'twn_time', 'twn_float', 'twn_vector',
    'twn_complete', 'twn_kill', 'twn_flip', 'twn_goto', 'twn_pause', 'twn_play', 'twn_play_backwards',
    'twn_play_forward', 'twn_restart', 'twn_rewind', 'twn_smooth_rewind', 'twn_toggle_pause',
    'get_time_scale', 'set_time_scale', 'twn_pivot', 'twn_pivot_x', 'twn_pivot_y',
]


# Module attributes forward the default manager's mutable settings.
# Forward writes as well as reads: assigning a setting must affect playback.
import sys as _sys
from types import ModuleType as _ModuleType

_CONFIG_FIELDS = frozenset((
    "time_scale", "unscaled_time_scale", "use_safe_mode", "log_behaviour", "draw_gizmos", "show_editor_report",
    "use_smooth_delta_time", "max_smooth_unscaled_time",
    "nested_tween_failure_behaviour", "default_recyclable", "default_update_type",
    "default_time_scale_independent", "default_auto_kill", "default_auto_play",
    "default_loop_type", "default_ease_type", "default_ease_overshoot_or_amplitude",
    "default_ease_period",
    "debug_mode", "debug_store_target_id",
    "safe_mode_log_behaviour", "rewind_callback_mode", "on_will_log",
))
__all__.extend(sorted(_CONFIG_FIELDS))


class _TweenModule(_ModuleType):
    def __dir__(self):
        return sorted(set(super().__dir__()) | _CONFIG_FIELDS | {"instance"})

    def __getattr__(self, name):
        if name == "instance":
            return _default_manager if _default_manager._initialized else None
        if name in _CONFIG_FIELDS:
            return getattr(_default_manager, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name, value):
        if name == "instance":
            raise AttributeError("instance is read-only")
        if name in _CONFIG_FIELDS:
            setattr(_default_manager, name, value)
        else:
            super().__setattr__(name, value)


_sys.modules[__name__].__class__ = _TweenModule
