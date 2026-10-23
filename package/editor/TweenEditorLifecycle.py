from infernux.engine.play_mode import PlayModeState
from infernux.lifecycle import InxPreload


class TweenEditorLifecycle(InxPreload):
    def preload(self, context):
        if context.engine is None:
            return
        from infernux_tween import _default_manager

        manager = context.engine.get_play_mode_manager()

        def state_changed(event):
            if event.new_state not in (PlayModeState.PLAYING, PlayModeState.PAUSED):
                _default_manager.clear()

        manager.add_state_change_listener(state_changed)
        context.add_cleanup(lambda: manager.remove_state_change_listener(state_changed))
