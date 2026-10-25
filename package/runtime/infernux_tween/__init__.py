"""Tween and sequence playback for Infernux."""
from math import isfinite

from .core import (
    AutoPlay, AxisConstraint, LoopType, OnEnableBehaviour, OnDisableBehaviour,
    Sequence, Tween, Tweener, TweenManager, TweenParams, UpdateType, VisualManagerPreset, _default_manager,
)
from .curve import EaseCurve
from .ease import Ease, stop_motion
from .link import LinkBehaviour
from .motion import ShakeRandomnessMode, SpiralMode
from .path import Path, PathMode, PathType, PathTween
from .rotation import RotateMode
from .spring import Spring
from .string import ScrambleMode
from .text import SkewSpanMode, TextTweenAnimator
from .virtual import delayed_call, eased_value
from .shortcuts import Color2, CultureInfo
from .shortcuts import (
    do_path,
    do_local_path,
    do_rotate_quaternion,
    do_local_rotate_quaternion,
    do_blendable_local_move_by,
    do_blendable_move_by,
    do_blendable_scale_by,
    do_blendable_rotate_by,
    do_blendable_local_rotate_by,
    do_spiral,
    do_jump,
    do_local_jump,
    do_punch_position,
    do_punch_rotation,
    do_punch_scale,
    do_shake_position,
    do_shake_rotation,
    do_shake_scale,
    do_move,
    do_local_move,
    do_scale,
    do_rotate,
    do_local_rotate,
    do_look_at,
    do_dynamic_look_at,
    do_color,
    do_blendable_color,
    do_fade,
    do_gradient_color,
    do_value,
    do_size_delta,
    do_text,
    do_counter,
    do_max_visible_characters,
    do_move_x,
    do_move_y,
    do_move_z,
    do_local_move_x,
    do_local_move_y,
    do_local_move_z,
    do_scale_x,
    do_scale_y,
    do_scale_z,
    do_pitch,
    do_intensity,
    do_shadow_strength,
    do_field_of_view,
    do_ortho_size,
    do_near_clip_plane,
    do_far_clip_plane,
    do_font_size,
    do_time_scale,
    do_float,
    do_vector,
    do_complete,
    do_kill,
    do_flip,
    do_goto,
    do_pause,
    do_play,
    do_play_backwards,
    do_play_forward,
    do_restart,
    do_rewind,
    do_smooth_rewind,
    do_toggle_pause,
)
from .motion import do_blendable_punch_rotation

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
clear = _default_manager.clear


def get_time_scale() -> float:
    return _default_manager.time_scale


def set_time_scale(value: float) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError("time_scale must be finite and nonnegative")
    _default_manager.time_scale = value


__all__ = [
    'SkewSpanMode', 'do_blendable_punch_rotation', 'AutoPlay', 'AxisConstraint', 'Ease', 'EaseCurve',
    'OnEnableBehaviour', 'OnDisableBehaviour', 'VisualManagerPreset',
    'virtual', 'delayed_call', 'eased_value', 'stop_motion',
    'LinkBehaviour', 'LoopType', 'Path', 'PathMode', 'PathType', 'PathTween', 'RotateMode',
    'ScrambleMode', 'Sequence', 'ShakeRandomnessMode', 'SpiralMode', 'Spring', 'TextTweenAnimator',
    'Tween', 'Tweener', 'TweenManager', 'TweenParams', 'Color2', 'CultureInfo', 'UpdateType', 'add',
    'to', 'to_axis', 'to_alpha', 'to_array', 'punch', 'shake', 'sequence', 'update', 'manual_update',
    'play_all', 'play', 'play_forward_all', 'play_forward', 'play_backwards_all', 'play_backwards',
    'pause_all', 'pause', 'flip_all', 'flip', 'restart_all', 'restart', 'rewind_all', 'rewind',
    'smooth_rewind_all', 'smooth_rewind', 'toggle_pause_all', 'toggle_pause', 'complete_all',
    'complete', 'kill_all', 'kill',
    'goto_all', 'goto', 'is_tweening', 'tweens_by_id', 'tweens_by_target', 'playing_tweens',
    'paused_tweens', 'total_active_tweens', 'total_active_tweeners', 'total_active_sequences',
    'total_tweens_by_id', 'total_playing_tweens', 'get_diagnostics', 'clear', 'do_path',
    'do_local_path', 'do_rotate_quaternion', 'do_local_rotate_quaternion', 'do_blendable_local_move_by',
    'do_blendable_move_by', 'do_blendable_scale_by', 'do_blendable_rotate_by',
    'do_blendable_local_rotate_by', 'do_spiral', 'do_jump', 'do_local_jump', 'do_punch_position',
    'do_punch_rotation', 'do_punch_scale', 'do_shake_position', 'do_shake_rotation', 'do_shake_scale',
    'do_move', 'do_local_move', 'do_scale', 'do_rotate', 'do_local_rotate', 'do_look_at',
    'do_dynamic_look_at', 'do_color', 'do_blendable_color', 'do_fade', 'do_gradient_color', 'do_value',
    'do_size_delta', 'do_text', 'do_counter', 'do_max_visible_characters', 'do_move_x', 'do_move_y',
    'do_move_z', 'do_local_move_x', 'do_local_move_y', 'do_local_move_z', 'do_scale_x', 'do_scale_y',
    'do_scale_z', 'do_pitch', 'do_intensity', 'do_shadow_strength', 'do_field_of_view', 'do_ortho_size',
    'do_near_clip_plane', 'do_far_clip_plane', 'do_font_size', 'do_time_scale', 'do_float', 'do_vector',
    'do_complete', 'do_kill', 'do_flip', 'do_goto', 'do_pause', 'do_play', 'do_play_backwards',
    'do_play_forward', 'do_restart', 'do_rewind', 'do_smooth_rewind', 'do_toggle_pause',
    'get_time_scale', 'set_time_scale',
]
