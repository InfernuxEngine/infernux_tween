from enum import Enum

from infernux.components import InxComponent, add_component_menu, serialized_field
from infernux.lib import SceneManager
from infernux_tween.authoring import TweenAuthoring


class ActivationAction(str, Enum):
    None_ = "None"
    Play = "Play"
    PlayForward = "PlayForward"
    PlayBackwards = "PlayBackwards"
    Pause = "Pause"
    Restart = "Restart"
    Rewind = "Rewind"
    Complete = "Complete"
    Kill = "Kill"


@add_component_menu("Animation/Tween Visual Manager")
class DOTweenVisualManager(InxComponent):
    on_enable_action: ActivationAction = serialized_field(default=ActivationAction.Restart, display_name_key="tween.enable_action",
                                                         enum_labels=["tween.action."+e.name for e in ActivationAction])
    on_disable_action: ActivationAction = serialized_field(default=ActivationAction.Pause, display_name_key="tween.disable_action",
                                                          enum_labels=["tween.action."+e.name for e in ActivationAction])

    def _apply(self, action):
        if action == ActivationAction.None_ or not SceneManager.instance().is_playing():
            return
        for component in self.game_object.get_components(TweenAuthoring):
            if component.GetTween() is None:
                component.CreateTween()
            getattr(component, "DO" + action.name)()

    def on_enable(self): self._apply(self.on_enable_action)
    def on_disable(self): self._apply(self.on_disable_action)
