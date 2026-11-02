import numpy as np

from infernux import editor
from infernux.editor import EditorPanel, PanelInteractionDescriptor, editor_panel, translate
from infernux.engine.interaction import SelectionService
from infernux.engine.interaction.handles import register_handle_provider
from infernux.gizmos import Gizmos
from infernux.lib import SceneManager
from infernux.lifecycle import InxPreload


from .TweenPathEditor import draw_inspector, waypoint_handle


_context = None


def _report_play_state(event):
    from infernux.engine.play_mode import PlayModeState
    from infernux_tween import _default_manager
    if event.new_state == PlayModeState.ENTERING:
        from infernux_tween import TweenEditorPreview
        TweenEditorPreview.stop(reset_tween_targets=True)
        _default_manager._reset_editor_report()
    elif (event.new_state == PlayModeState.EDIT
          and event.old_state in (PlayModeState.PLAYING, PlayModeState.PAUSED, PlayModeState.RESTORING)
          and _default_manager.show_editor_report):
        from infernux.debug import Debug
        report = _default_manager.get_editor_report()
        Debug.log("Tween Play report: peak roots "
                  f"{report['peak_tweeners']} tweeners / {report['peak_sequences']} sequences; "
                  f"{report['safe_mode_errors']} handled errors")


def _draw_paths(ctx):
    if SceneManager.instance().is_playing():
        from infernux_tween import PathTween, _default_manager
        if not _default_manager.draw_gizmos:
            return
        previous = Gizmos.color
        try:
            for path in _default_manager._matching():
                if not isinstance(path, PathTween) or path._path is None:
                    continue
                points = path.path_get_draw_points()
                transform = path._path_target.transform if path._body else path._path_target
                if path.local and transform.parent is not None:
                    points = [transform.parent.transform_point(point) for point in points]
                Gizmos.color = tuple(path.gizmo_color[:3])
                indices = np.column_stack((np.arange(len(points)-1), np.arange(1, len(points))))
                Gizmos.draw_lines(np.asarray([tuple(point) for point in points], dtype=np.float32), indices)
        finally:
            Gizmos.color = previous
        return
    for identifier in SelectionService.instance().scene_object_ids():
        obj = SceneManager.instance().find_runtime_object_by_id(identifier)
        if obj is None:
            continue
        for component in obj.get_components("TweenPath"):
            if component._preview_manager is not None:
                continue
            points = getattr(component, "_editor_frozen_draw_points", None)
            if points is None:
                try:
                    points = component.get_world_draw_points()
                except ValueError:
                    points = ()  # Allow editing an incomplete Bezier route.
            if len(points) > 1:
                previous = Gizmos.color
                Gizmos.color = tuple(component.path_color[:3])
                try:
                    indices = np.column_stack((np.arange(len(points)-1), np.arange(1, len(points))))
                    Gizmos.draw_lines(np.asarray(points, dtype=np.float32), indices)
                finally:
                    Gizmos.color = previous
            for index in range(len(component.waypoints)):
                waypoint_handle(ctx, component, index)


class TweenTools(InxPreload):
    def preload(self, context):
        global _context
        _context = context
        from infernux_tween import TweenEditorPreview
        context.add_cleanup(lambda: TweenEditorPreview.stop(reset_tween_targets=True))
        from infernux.engine.play_mode import PlayModeManager
        play_mode = PlayModeManager.instance()
        if play_mode is not None:
            play_mode.add_state_change_listener(_report_play_state)
            context.add_cleanup(lambda: play_mode.remove_state_change_listener(_report_play_state))
        registration = register_handle_provider("infernux.tween.paths", _draw_paths)
        context.add_cleanup(registration.close)
        from infernux.engine.ui.inspector_components import (
            register_py_component_extra_renderer, register_py_component_renderer,
        )
        from .TweenEvents import draw_events, _cached_methods
        register_py_component_renderer('TweenPath', draw_inspector)
        context.add_cleanup(lambda: register_py_component_renderer('TweenPath', None))
        for name in ('TweenAnimation',):
            register_py_component_extra_renderer(name, draw_events)
            context.add_cleanup(lambda name=name: register_py_component_extra_renderer(name, None))
        context.add_cleanup(_cached_methods.cache_clear)


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
            from infernux_tween import TweenInspectorMode
            for component in self._components:
                if getattr(component, "inspector_mode", None) != TweenInspectorMode.ONLY_PATH:
                    component.begin_preview(scope)
        except BaseException:
            scope.close()
            raise
        self._scope = scope

    def on_render_content(self, ctx):
        from infernux_tween import _default_manager
        diagnostics = _default_manager.get_diagnostics()
        ctx.label(translate("tween.diagnostics").format(**diagnostics))
        ctx.label(" / ".join(translate("tween.clock."+phase)+": "+str(counts["playing"])
                             for phase, counts in diagnostics["phases"].items()))
        settings = _default_manager._settings
        if settings is not None:
            if settings.show_playing_tweens:
                self._draw_tweens(ctx, _default_manager.playing_tweens(), "▶")
            if settings.show_paused_tweens:
                self._draw_tweens(ctx, _default_manager.paused_tweens(), "Ⅱ")
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
        if settings is not None and not settings.show_preview_panel:
            return
        if ctx.button(translate("tween.preview")):
            editor.defer(self._start, description=translate("tween.preview"))
        ctx.same_line()
        if ctx.button(translate("tween.stop_restore")):
            editor.defer(self._stop, description=translate("tween.stop_restore"))
        if self._scope is not None and not self._scope.closed:
            if ctx.button(translate("tween.pause")):
                for component in self._components:
                    component.twn_pause()
            ctx.same_line()
            if ctx.button(translate("tween.play")):
                for component in self._components:
                    component.twn_play()

    @staticmethod
    def _draw_tweens(ctx, handles, prefix):
        for handle in handles or ():
            if handle.string_id is not None:
                identity = handle.string_id
            elif handle.int_id != -999:
                identity = handle.int_id
            else:
                identity = handle.id if handle.id is not None else type(handle).__name__
            ctx.label(f"{prefix} {identity}: {handle.elapsed():.3f} / {handle.duration():.3f}")
