import importlib.util
from pathlib import Path
from types import SimpleNamespace

from infernux.engine.play_mode import PlayModeState
from infernux_tween import DOTween


def test_editor_stop_clears_global_tweens_and_unload_releases_the_listener():
    path = Path(__file__).resolve().parents[1] / "package/editor/TweenEditorLifecycle.py"
    spec = importlib.util.spec_from_file_location("tween_editor_lifecycle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    listeners, cleanups = [], []
    manager = SimpleNamespace(add_state_change_listener=listeners.append, remove_state_change_listener=listeners.remove)
    context = SimpleNamespace(engine=SimpleNamespace(get_play_mode_manager=lambda: manager), add_cleanup=cleanups.append)
    try:
        module.TweenEditorLifecycle().preload(context)
        tween = DOTween.To(lambda: 0, lambda value: None, 1, 1)
        listeners[0](SimpleNamespace(new_state=PlayModeState.PAUSED))
        assert tween.IsActive()
        listeners[0](SimpleNamespace(new_state=PlayModeState.RESTORING))
        assert not tween.IsActive() and not any(DOTween._running.values())
        cleanups[0]()
        assert not listeners
    finally:
        DOTween.Clear()
