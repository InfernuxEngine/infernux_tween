"""Author tween defaults as an engine DataAsset and apply them before playback."""
from infernux.components import SerializableObject, get_serialized_fields, serialized_field
from infernux.core import DataAsset

from .core import (
    AutoPlay, LogBehaviour, LoopType, NestedTweenFailureBehaviour, RewindCallbackMode,
    SafeModeLogBehaviour, UpdateType,
)
from .ease import Ease


class SafeModeOptions(SerializableObject):
    __serialized_type_id__ = "infernux.tween.safe_mode_options"

    log_behaviour: SafeModeLogBehaviour = serialized_field(default=SafeModeLogBehaviour.WARNING)
    nested_tween_failure_behaviour: NestedTweenFailureBehaviour = serialized_field(
        default=NestedTweenFailureBehaviour.TRY_TO_PRESERVE_SEQUENCE)


class TweenSettings(DataAsset):
    __serialized_type_id__ = "infernux.tween.settings"
    asset_name = "TweenSettings"
    asset_full_filename = "TweenSettings.inxdata"
    SafeModeOptions = SafeModeOptions

    use_safe_mode: bool = serialized_field(default=True)
    safe_mode_options: SafeModeOptions = serialized_field(default_factory=SafeModeOptions)
    time_scale: float = serialized_field(default=1.)
    unscaled_time_scale: float = serialized_field(default=1.)
    use_smooth_delta_time: bool = serialized_field(default=False)
    max_smooth_unscaled_time: float = serialized_field(default=.15)
    rewind_callback_mode: RewindCallbackMode = serialized_field(default=RewindCallbackMode.FIRE_IF_POSITION_CHANGED)
    show_editor_report: bool = serialized_field(default=False)
    log_behaviour: LogBehaviour = serialized_field(default=LogBehaviour.DEFAULT)
    draw_gizmos: bool = serialized_field(default=True)
    default_recyclable: bool = serialized_field(default=False)
    default_auto_play: AutoPlay = serialized_field(default=AutoPlay.ALL)
    default_update_type: UpdateType = serialized_field(default=UpdateType.NORMAL)
    default_time_scale_independent: bool = serialized_field(default=False)
    default_ease_type: Ease = serialized_field(default=Ease.OUT_QUAD)
    default_ease_overshoot_or_amplitude: float = serialized_field(default=1.70158)
    default_ease_period: float = serialized_field(default=0.)
    default_auto_kill: bool = serialized_field(default=True)
    default_loop_type: LoopType = serialized_field(default=LoopType.RESTART)
    debug_mode: bool = serialized_field(default=False)
    debug_store_target_id: bool = serialized_field(default=True)
    show_preview_panel: bool = serialized_field(default=True)
    show_playing_tweens: bool = serialized_field(default=False)
    show_paused_tweens: bool = serialized_field(default=False)

    def apply(self, manager=None):
        """Apply runtime controls and defaults for subsequently created tweens."""
        if manager is None:
            from . import _default_manager
            manager = _default_manager
        for name in _MANAGER_FIELDS:
            setattr(manager, name, getattr(self, name))
        options = self.safe_mode_options
        manager.safe_mode_log_behaviour = options.log_behaviour
        manager.nested_tween_failure_behaviour = options.nested_tween_failure_behaviour
        manager._settings = self


_MANAGER_FIELDS = tuple(
    name for name in get_serialized_fields(TweenSettings)
    if name not in {"safe_mode_options", "show_preview_panel", "show_playing_tweens", "show_paused_tweens"}
)
