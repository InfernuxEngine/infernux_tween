from enum import Enum

from infernux.components import InxComponent, add_component_menu, serialized_field
from infernux.lib import SceneManager
from .TweenAuthoring import TweenAuthoring


class ActivationAction(Enum):
    NONE = "None"
    PLAY = "Play"
    PLAY_FORWARD = "PlayForward"
    PLAY_BACKWARDS = "PlayBackwards"
    PAUSE = "Pause"
    RESTART = "Restart"
    REWIND = "Rewind"
    COMPLETE = "Complete"
    KILL = "Kill"


@add_component_menu("Animation/Tween Visual Manager")
class TweenVisualManager(InxComponent):
    on_enable_action: ActivationAction = serialized_field(default=ActivationAction.RESTART, display_name_key="tween.enable_action",
                                                         enum_labels=["tween.action."+e.name for e in ActivationAction])
    on_disable_action: ActivationAction = serialized_field(default=ActivationAction.PAUSE, display_name_key="tween.disable_action",
                                                          enum_labels=["tween.action."+e.name for e in ActivationAction])

    def _apply(self, action):
        if action == ActivationAction.NONE or not SceneManager.instance().is_playing():
            return
        components = self.game_object.get_components(TweenAuthoring)
        for component in components:
            if component.get_tween() is None:
                component.create_tween()
        groups = set()
        for component in components:
            group = id(component._group_target())
            if group in groups:
                continue
            groups.add(group)
            getattr(component, "do_" + action.name.lower())()

    def on_enable(self): self._apply(self.on_enable_action)
    def on_disable(self): self._apply(self.on_disable_action)
