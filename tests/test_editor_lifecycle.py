import importlib.util
from pathlib import Path
from types import SimpleNamespace

from infernux.engine.play_mode import PlayModeState
import infernux_tween as tween


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
        active = tween.to(lambda: 0, lambda value: None, 1, 1)
        listeners[0](SimpleNamespace(new_state=PlayModeState.PAUSED))
        assert active.is_active()
        listeners[0](SimpleNamespace(new_state=PlayModeState.RESTORING))
        assert not active.is_active() and not tween.total_active_tweens()
        cleanups[0]()
        assert not listeners
    finally:
        tween.clear()
