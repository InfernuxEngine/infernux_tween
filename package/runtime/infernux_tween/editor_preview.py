"""Scripted Edit-mode previews on the engine's shared frame scheduler."""
from .core import UpdateType, _default_manager


class _PreviewMeta(type):
    @property
    def is_previewing(cls):
        return cls._registration is not None


class TweenEditorPreview(metaclass=_PreviewMeta):
    _registration = None
    _on_preview_updated = None
    _tweens = []

    @classmethod
    def prepare_tween_for_preview(cls, tween, clear_callbacks=True, prevent_auto_kill=True, and_play=True):
        cls._tweens.append(tween)
        tween.set_update(UpdateType.MANUAL)
        if prevent_auto_kill:
            tween.set_auto_kill(False)
        if clear_callbacks:
            tween._callbacks.clear()
        if and_play:
            tween.play()

    @classmethod
    def start(cls, on_preview_updated=None):
        from infernux.lib import SceneManager
        from infernux.runtime_services import register_update

        if cls.is_previewing or SceneManager.instance().is_playing():
            return
        cls._on_preview_updated = on_preview_updated
        cls._registration = register_update(cls._tick, phase="editor_update")

    @classmethod
    def _tick(cls, delta):
        _default_manager.manual_update(delta, delta)
        callback = cls._on_preview_updated
        if callback is not None:
            callback()

    @classmethod
    def stop(cls, reset_tween_targets=False, clear_tweens=True):
        registration, cls._registration = cls._registration, None
        cls._on_preview_updated = None
        if registration is not None:
            registration.close()
        if reset_tween_targets:
            # Configuration-time work only; preview ticks retain normal tween
            # ordering and never copy or inspect scene properties themselves.
            for tween in tuple(cls._tweens):
                if tween._active:
                    tween.complete() if getattr(tween, "_from", False) else tween.rewind()
        if clear_tweens:
            cls._tweens.clear()
        else:
            cls._tweens[:] = [tween for tween in cls._tweens if tween._active]
