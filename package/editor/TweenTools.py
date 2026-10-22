import numpy as np

from infernux import editor
from infernux.editor import EditorPanel, PanelInteractionDescriptor, editor_panel, translate
from infernux.engine.interaction import SelectionService
from infernux.engine.interaction.components import ComponentCommandService
from infernux.engine.interaction.handles import register_handle_provider
from infernux.engine.interaction.previews import close_editor_previews
from infernux.gizmos import Gizmos
from infernux.lib import SceneManager
from infernux.lifecycle import InxPreload


_context = None


def _waypoint_handle(ctx, component, index):
    before = []

    def begin(_value):
        close_editor_previews()
        before[:] = [tuple(p) for p in component.waypoints]

    def changed(value):
        points = list(component.waypoints)
        points[index] = component.WaypointFromWorld(value)
        component.waypoints = points

    def commit(_value):
        after = list(component.waypoints)
        component.waypoints = list(before)
        ComponentCommandService.require().set_field(component, "waypoints", after,
                                                    description=translate("tween.move_waypoint"))

    def cancel(_value):
        if component.is_valid:
            component.waypoints = list(before)

    ctx.position(f"path-{component.component_id}-{index}", component.WorldWaypoint(index), changed,
                 on_begin=begin, on_commit=commit, on_cancel=cancel)


def _draw_paths(ctx):
    for identifier in SelectionService.instance().scene_object_ids():
        obj = SceneManager.instance().find_runtime_object_by_id(identifier)
        if obj is None:
            continue
        for component in obj.get_components("DOTweenPath"):
            if component._preview_manager is not None:
                continue
            points = component.DrawPoints()
            if len(points) > 1:
                previous = Gizmos.color
                Gizmos.color = (0.95, 0.7, 0.3)
                try:
                    indices = np.column_stack((np.arange(len(points)-1), np.arange(1, len(points))))
                    Gizmos.draw_lines(np.asarray(points, dtype=np.float32), indices)
                finally:
                    Gizmos.color = previous
            for index in range(len(component.waypoints)):
                _waypoint_handle(ctx, component, index)


class TweenTools(InxPreload):
    def preload(self, context):
        global _context
        _context = context
        registration = register_handle_provider("infernux.tween.paths", _draw_paths,
                                                enabled=lambda: not SceneManager.instance().is_playing())
        context.add_cleanup(registration.close)


@editor_panel("Tween", type_id="infernux.tween.tools", title_key="tween.panel", menu_path="Animation",
              interaction=PanelInteractionDescriptor())
class TweenPanel(EditorPanel):
    def __init__(self):
        super().__init__(translate("tween.panel"))
        self._components = []
        self._scope = None

    def _initial_size(self): return (440, 220)

    def on_enable(self):
        SelectionService.instance().add_listener(self._selection_changed)
        self.services.play_mode_manager.add_state_change_listener(self._selection_changed)
        self._bind_selection()

    def on_disable(self):
        SelectionService.instance().remove_listener(self._selection_changed)
        self.services.play_mode_manager.remove_state_change_listener(self._selection_changed)
        self._stop()

    def _selection_changed(self, _event):
        self._stop()
        self._bind_selection()

    def _bind_selection(self):
        from ..runtime.TweenAuthoring import TweenAuthoring
        self._components = []
        for identifier in SelectionService.instance().scene_object_ids():
            obj = SceneManager.instance().find_runtime_object_by_id(identifier)
            if obj is not None:
                self._components.extend(obj.get_components(TweenAuthoring))

    def _stop(self):
        if self._scope is not None:
            self._scope.close()
            self._scope = None

    def _start(self):
        self._stop()
        scope = _context.create_preview()
        try:
            for component in self._components:
                component.BeginPreview(scope)
        except BaseException:
            scope.close()
            raise
        self._scope = scope

    def on_render_content(self, ctx):
        from infernux_tween import DOTween
        diagnostics = DOTween.GetDiagnostics()
        ctx.label(translate("tween.diagnostics").format(**diagnostics))
        ctx.label(" / ".join(translate("tween.clock."+phase)+": "+str(counts["playing"])
                             for phase, counts in diagnostics["phases"].items()))
        if any(not c.is_valid for c in self._components):
            self._stop()
            self._bind_selection()
        if not self._components:
            ctx.label(translate("tween.select_hint"))
            return
        ctx.label(translate("tween.configure_hint"))
        for component in self._components:
            ctx.label(f"{component.game_object.name} / {type(component).__name__}")
        if self.services.play_mode_manager.is_playing:
            ctx.label(translate("tween.edit_hint"))
            return
        if ctx.button(translate("tween.preview")):
            editor.defer(self._start, description=translate("tween.preview"))
        ctx.same_line()
        if ctx.button(translate("tween.stop_restore")):
            editor.defer(self._stop, description=translate("tween.stop_restore"))
        if self._scope is not None and not self._scope.closed:
            if ctx.button(translate("tween.pause")):
                for component in self._components:
                    component.DOPause()
            ctx.same_line()
            if ctx.button(translate("tween.play")):
                for component in self._components:
                    component.DOPlay()
