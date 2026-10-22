"""Object lifecycle links remain effective while every tween is paused."""
from enum import Enum

from infernux.components import InxComponent, disallow_multiple


class LinkBehaviour(str, Enum):
    KillOnDestroy = "KillOnDestroy"
    KillOnDisable = "KillOnDisable"
    PauseOnDisable = "PauseOnDisable"
    PauseOnDisablePlayOnEnable = "PauseOnDisablePlayOnEnable"
    PauseOnDisableRestartOnEnable = "PauseOnDisableRestartOnEnable"
    PlayOnEnable = "PlayOnEnable"
    RestartOnEnable = "RestartOnEnable"
    CompleteOnDisable = "CompleteOnDisable"
    CompleteAndKillOnDisable = "CompleteAndKillOnDisable"
    RewindOnDisable = "RewindOnDisable"
    RewindAndKillOnDisable = "RewindAndKillOnDisable"


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
        if behaviour == LinkBehaviour.KillOnDisable:
            tween.Kill()
        elif behaviour in (LinkBehaviour.PauseOnDisable, LinkBehaviour.PauseOnDisablePlayOnEnable,
                            LinkBehaviour.PauseOnDisableRestartOnEnable):
            tween.Pause()
        elif behaviour in (LinkBehaviour.CompleteOnDisable, LinkBehaviour.CompleteAndKillOnDisable):
            tween.Complete()
            if behaviour == LinkBehaviour.CompleteAndKillOnDisable:
                tween.Kill()
        elif behaviour in (LinkBehaviour.RewindOnDisable, LinkBehaviour.RewindAndKillOnDisable):
            tween.Rewind()
            if behaviour == LinkBehaviour.RewindAndKillOnDisable:
                tween.Kill()

    def on_disable(self):
        for tween, behaviour in tuple(self._entries.items()):
            self._disable(tween, behaviour)

    def on_enable(self):
        for tween, behaviour in tuple(self._entries.items()):
            if behaviour in (LinkBehaviour.PlayOnEnable, LinkBehaviour.PauseOnDisablePlayOnEnable):
                tween.Play()
            elif behaviour in (LinkBehaviour.RestartOnEnable, LinkBehaviour.PauseOnDisableRestartOnEnable):
                tween.Restart()

    def on_destroy(self):
        for tween in tuple(self._entries):
            tween.Kill()
