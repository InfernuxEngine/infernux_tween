"""Tween defaults share the engine's editable and cooked DataAsset formats."""
from infernux.components import get_serialized_fields
from infernux.core import DataAsset
from infernux.core.data_asset import encode_data_asset_artifact, decode_data_asset_artifact
import infernux_tween as tween
from infernux_tween import (
    AutoPlay, Ease, LogBehaviour, LoopType, NestedTweenFailureBehaviour,
    RewindCallbackMode, SafeModeLogBehaviour, SafeModeOptions, TweenManager,
    TweenSettings, UpdateType,
)


def test_settings_roundtrip_through_player_asset_format_and_drive_new_tweens():
    source = TweenSettings(
        default_ease_type=Ease.LINEAR, default_update_type=UpdateType.MANUAL,
        default_loop_type=LoopType.YOYO, default_auto_kill=False,
        default_recyclable=True, default_time_scale_independent=True,
        rewind_callback_mode=RewindCallbackMode.FIRE_ALWAYS_WITH_REWIND,
        time_scale=.5, unscaled_time_scale=2., log_behaviour=LogBehaviour.ERRORS_ONLY,
        safe_mode_options=SafeModeOptions(log_behaviour=SafeModeLogBehaviour.ERROR,
            nested_tween_failure_behaviour=NestedTweenFailureBehaviour.KILL_WHOLE_SEQUENCE),
    )
    payload = encode_data_asset_artifact(source.serialize_document())
    restored = DataAsset.from_document(decode_data_asset_artifact(payload))
    assert type(restored) is TweenSettings
    assert restored.serialize_document() == source.serialize_document()
    manager, values = TweenManager(), [0.]
    assert restored.apply(manager) is None
    handle = manager.to(lambda: values[0], lambda value: values.__setitem__(0, value), 1., 1.)
    try:
        assert handle.update_type is UpdateType.MANUAL and handle.independent
        assert handle.loop_type is LoopType.YOYO and handle.recyclable and not handle.auto_kill
        assert manager.rewind_callback_mode is RewindCallbackMode.FIRE_ALWAYS_WITH_REWIND
        assert manager.safe_mode_log_behaviour is SafeModeLogBehaviour.ERROR
        assert manager.nested_tween_failure_behaviour is NestedTweenFailureBehaviour.KILL_WHOLE_SEQUENCE
        manager.manual_update(.25, .5)
        assert values == [.5]
    finally:
        manager.clear(True)
    assert manager._settings is None


def test_applying_new_defaults_preserves_existing_tween_configuration():
    manager, values = TweenManager(), [0., 0.]
    first = manager.to(lambda: values[0], lambda x: values.__setitem__(0, x), 1., 1.).set_ease(Ease.LINEAR)
    TweenSettings(default_ease_type=Ease.IN_QUAD, default_auto_kill=False,
                  default_auto_play=AutoPlay.NONE).apply(manager)
    second = manager.to(lambda: values[1], lambda x: values.__setitem__(1, x), 1., 1.)
    try:
        assert first.auto_kill and first.is_playing()
        assert not second.auto_kill and not second.is_playing()
        second.play()
        manager.update(.5)
        assert values == [.5, .25]
    finally:
        manager.clear()


def test_nested_options_have_independent_asset_ownership_and_editable_fields():
    first, second = TweenSettings(), TweenSettings()
    first.safe_mode_options.log_behaviour = SafeModeLogBehaviour.NONE
    assert second.safe_mode_options.log_behaviour is SafeModeLogBehaviour.WARNING
    assert "rewind_callback_mode" in get_serialized_fields(TweenSettings)
    assert TweenSettings.SafeModeOptions is SafeModeOptions
    assert first.asset_full_filename.endswith(".inxdata")


def test_asset_can_apply_to_the_default_module_manager(monkeypatch):
    manager = TweenManager()
    monkeypatch.setattr(tween, "_default_manager", manager)
    settings = TweenSettings(use_safe_mode=False, debug_mode=True, debug_store_target_id=False)
    settings.apply()
    try:
        assert not tween.use_safe_mode and tween.debug_mode
        assert not manager._debug_store_target_id and manager._settings is settings
    finally:
        manager.clear(True)
