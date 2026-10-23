"""Object lifecycle links remain effective while every tween is paused."""
from enum import Enum

from infernux.components import InxComponent, disallow_multiple


class LinkBehaviour(Enum):
    KILL_ON_DESTROY = "KillOnDestroy"
    KILL_ON_DISABLE = "KillOnDisable"
    PAUSE_ON_DISABLE = "PauseOnDisable"
    PAUSE_ON_DISABLE_PLAY_ON_ENABLE = "PauseOnDisablePlayOnEnable"
    PAUSE_ON_DISABLE_RESTART_ON_ENABLE = "PauseOnDisableRestartOnEnable"
    PLAY_ON_ENABLE = "PlayOnEnable"
    RESTART_ON_ENABLE = "RestartOnEnable"
    COMPLETE_ON_DISABLE = "CompleteOnDisable"
    COMPLETE_AND_KILL_ON_DISABLE = "CompleteAndKillOnDisable"
    REWIND_ON_DISABLE = "RewindOnDisable"
    REWIND_AND_KILL_ON_DISABLE = "RewindAndKillOnDisable"


@disallow_multiple
class TweenLink(InxComponent):
    @property
    def _entries(self):
        return self.__dict__.setdefault("_linked_tweens", {})

    def bind(self, tween, behaviour):
        self._entries[tween] = behaviour
        tween._link = self
        if not self.game_object.active_in_hierarchy:
            self._disable(tween, behaviour)

    def detach(self, tween):
        self._entries.pop(tween, None)
        tween._link = None

    def _disable(self, tween, behaviour):
        if behaviour == LinkBehaviour.KILL_ON_DISABLE:
            tween.kill()
        elif behaviour in (LinkBehaviour.PAUSE_ON_DISABLE, LinkBehaviour.PAUSE_ON_DISABLE_PLAY_ON_ENABLE,
                            LinkBehaviour.PAUSE_ON_DISABLE_RESTART_ON_ENABLE):
            tween.pause()
        elif behaviour in (LinkBehaviour.COMPLETE_ON_DISABLE, LinkBehaviour.COMPLETE_AND_KILL_ON_DISABLE):
            tween.complete()
            if behaviour == LinkBehaviour.COMPLETE_AND_KILL_ON_DISABLE:
                tween.kill()
        elif behaviour in (LinkBehaviour.REWIND_ON_DISABLE, LinkBehaviour.REWIND_AND_KILL_ON_DISABLE):
            tween.rewind()
            if behaviour == LinkBehaviour.REWIND_AND_KILL_ON_DISABLE:
                tween.kill()

    def on_disable(self):
        for tween, behaviour in tuple(self._entries.items()):
            self._disable(tween, behaviour)

    def on_enable(self):
        for tween, behaviour in tuple(self._entries.items()):
            if behaviour in (LinkBehaviour.PLAY_ON_ENABLE, LinkBehaviour.PAUSE_ON_DISABLE_PLAY_ON_ENABLE):
                tween.play()
            elif behaviour in (LinkBehaviour.RESTART_ON_ENABLE, LinkBehaviour.PAUSE_ON_DISABLE_RESTART_ON_ENABLE):
                tween.restart()

    def on_destroy(self):
        for tween in tuple(self._entries):
            tween.kill()
