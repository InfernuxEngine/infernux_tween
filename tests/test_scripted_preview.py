"""Script-created tweens use real editor frame registrations and native targets."""
import pytest

from infernux.lib import SceneManager, Vector3
from infernux.runtime_services import _dispatch_updates, _update_snapshot
import infernux_tween as tween
from infernux_tween import Ease, TweenEditorPreview as Preview, UpdateType


@pytest.fixture
def preview_object():
    manager = SceneManager.instance()
    scene = manager.create_scene("脚本预览测试")
    obj = scene.create_game_object("预览物体")
    obj.transform.position = Vector3(2, 0, 0)
    Preview.stop()
    tween.clear(True)
    try:
        yield obj
    finally:
        Preview.stop()
        tween.clear(True)
        if manager.is_playing():
            manager.stop()
        manager.unload_scene(scene)


def editor_tick(delta):
    _dispatch_updates(_update_snapshot()["editor_update"], delta, delta)


def test_prepare_start_tick_stop_and_reset_native_transform(preview_object):
    events = []
    target = preview_object.transform
    move = tween.twn_move(target, Vector3(6, 0, 0), 1).set_ease(Ease.LINEAR)
    move.on_update(lambda: events.append("game callback"))
    assert Preview.prepare_tween_for_preview(move) is None
    assert move.update_type is UpdateType.MANUAL and not move.auto_kill
    Preview.start(lambda: events.append("editor tick"))
    Preview.start(lambda: events.append("duplicate"))
    assert Preview.is_previewing and len(_update_snapshot()["editor_update"]) == 1
    editor_tick(.5)
    assert target.position.x == 4 and events == ["editor tick"]
    editor_tick(.5)
    assert target.position.x == 6 and move.is_active()
    Preview.stop(reset_tween_targets=True)
    assert target.position.x == 2 and not Preview.is_previewing
    assert not _update_snapshot()["editor_update"]
    editor_tick(1)
    assert events == ["editor tick", "editor tick"]


def test_prepare_options_keep_callbacks_autokill_and_pause(preview_object):
    events = []
    move = tween.twn_move(preview_object.transform, Vector3(6, 0, 0), 1)
    move.on_complete(lambda: events.append("done")).pause()
    Preview.prepare_tween_for_preview(move, clear_callbacks=False, prevent_auto_kill=False, and_play=False)
    assert not move.is_playing() and move.auto_kill
    Preview.start()
    editor_tick(1)
    assert not events
    move.play()
    editor_tick(1)
    assert events == ["done"] and not move.is_active()
    Preview.stop(clear_tweens=False)
    assert Preview._tweens == []


def test_stop_resets_from_tween_to_original_value(preview_object):
    target = preview_object.transform
    move = tween.twn_move(target, Vector3(6, 0, 0), 1).from_().set_ease(Ease.LINEAR)
    Preview.prepare_tween_for_preview(move)
    Preview.start()
    editor_tick(.5)
    assert target.position.x == 4
    Preview.stop(reset_tween_targets=True, clear_tweens=False)
    assert target.position.x == 2 and Preview._tweens == [move]


def test_start_ignores_play_mode(preview_object):
    manager = SceneManager.instance()
    manager.set_active_scene(preview_object.scene)
    manager.play()
    Preview.start()
    assert not Preview.is_previewing and not _update_snapshot()["editor_update"]


def test_preview_status_is_read_only():
    with pytest.raises(AttributeError):
        Preview.is_previewing = True
