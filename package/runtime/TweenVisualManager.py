from infernux.components import InxComponent, add_component_menu, serialized_field
from infernux.lib import SceneManager
from infernux_tween import OnEnableBehaviour, OnDisableBehaviour, VisualManagerPreset
from .TweenAuthoring import TweenAuthoring


@add_component_menu("Animation/Tween Visual Manager")
class TweenVisualManager(InxComponent):
    preset: VisualManagerPreset = serialized_field(default=VisualManagerPreset.CUSTOM, display_name_key="tween.preset",
        enum_labels=["tween.preset."+e.name for e in VisualManagerPreset])
    on_enable_behaviour: OnEnableBehaviour = serialized_field(default=OnEnableBehaviour.NONE, display_name_key="tween.enable_action",
        enum_labels=["tween.action."+e.name for e in OnEnableBehaviour])
    on_disable_behaviour: OnDisableBehaviour = serialized_field(default=OnDisableBehaviour.NONE, display_name_key="tween.disable_action",
        enum_labels=["tween.action."+e.name for e in OnDisableBehaviour])
    _restart_pending = False

    def on_validate(self):
        if self.preset == VisualManagerPreset.POOLING_SYSTEM:
            self.on_enable_behaviour = OnEnableBehaviour.RESTART_FROM_SPAWN_POINT
            self.on_disable_behaviour = OnDisableBehaviour.PAUSE

    def _apply(self, method):
        groups = set()
        for component in self.game_object.get_components(TweenAuthoring):
            if component.tween is None or not component.tween.is_active():
                continue
            group = (id(component._group_target()), type(component) if method == 'do_rewind' else None)
            if group not in groups:
                groups.add(group)
                getattr(component, method)()

    def on_enable(self):
        if not SceneManager.instance().is_playing():
            return
        if self.preset == VisualManagerPreset.POOLING_SYSTEM:
            self.on_validate()
            for component in self.game_object.get_components(TweenAuthoring):
                component.auto_kill = False
                if component.tween is not None:
                    component.tween.auto_kill = False
        action = self.on_enable_behaviour
        if action == OnEnableBehaviour.RESTART_FROM_SPAWN_POINT:
            self._restart_pending = True
        elif action != OnEnableBehaviour.NONE:
            self._apply('do_'+action.name.lower())

    def update(self, delta_time):
        if self._restart_pending:
            self._restart_pending = False
            for component in self.game_object.get_components(TweenAuthoring):
                if component.relative and component.tween is not None and component.tween.is_active():
                    component._restart_from_here()
            self._apply('do_restart')

    def on_disable(self):
        self._restart_pending = False
        if not SceneManager.instance().is_playing():
            return
        action = self.on_disable_behaviour
        if action == OnDisableBehaviour.KILL_AND_COMPLETE:
            self._apply('do_complete')
            self._apply('do_kill')
        elif action == OnDisableBehaviour.DESTROY_GAME_OBJECT:
            self._apply('do_kill')
            self.game_object.scene.destroy_game_object(self.game_object)
        elif action != OnDisableBehaviour.NONE:
            self._apply('do_'+action.name.lower())
