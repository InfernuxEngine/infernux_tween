"""Path authoring over the engine's shared handles, fields and Action Journal."""
from copy import deepcopy

from infernux import editor
from infernux.components import get_serialized_fields
from infernux.editor import translate
from infernux.engine.interaction.components import ComponentCommandService
from infernux.engine.interaction.previews import close_editor_previews
from infernux.engine.ui._inspector_list_field import _render_list_field
from infernux.engine.ui.inspector_components import render_py_component_fields
from infernux.lib import Physics, Vector3
from infernux_tween import HandlesDrawMode, HandlesType, TweenInspectorMode

from .TweenEvents import draw_events


_VISUAL_FIELDS = ("handles_type", "live_preview", "handles_draw_mode",
                  "perspective_handle_size", "show_indexes", "show_wp_length", "path_color")
_PATH_FIELDS = ("path_type", "path_mode", "resolution", "local", "close_path",
                "use_rigidbody", "orient_type", "look_ahead", "look_at_target",
                "look_at_position", "lock_rotation", "assign_forward_and_up",
                "forward_direction", "up_direction")


def _write_waypoints(component, points):
    """Keep an authored route and its editable world points in the same document."""
    component.waypoints = [tuple(point) for point in points]
    if component.full_wps:
        component.full_wps = [tuple(component.full_wps[0]), *component.waypoints]
        component._invalidate_authored_path()
    component._runtime_path = component._runtime_tween = None


def set_waypoints(component, points, *, description=None):
    points = [tuple(point) for point in points]
    return ComponentCommandService.require().edit_document(
        component, lambda: _write_waypoints(component, points),
        description=description or translate("tween.move_waypoint"), edit_key="waypoints",
    ).changed


def drop_to_floor(component):
    """Raycast down from each waypoint; keep misses and apply offset in world Y."""
    close_editor_previews()
    Physics.sync_transforms()
    points = []
    for index in range(len(component.waypoints)):
        world = component.world_waypoint(index)
        hit = Physics.raycast(world, Vector3(0, -1, 0), float.fromhex("0x1.fffffep+127"))
        if hit is not None:
            world = hit.point + Vector3(0, component.drop_to_floor_offset, 0)
        points.append(component.waypoint_from_world(world))
    return set_waypoints(component, points, description=translate("tween.drop_to_floor"))


def waypoint_handle(ctx, component, index):
    before = None

    def begin(_value):
        nonlocal before
        close_editor_previews()
        before = deepcopy(component._serialize_fields_document())
        if not component.live_preview:
            component._editor_frozen_draw_points = component.get_world_draw_points()

    def changed(value):
        points = list(component.waypoints)
        points[index] = component.waypoint_from_world(value)
        _write_waypoints(component, points)

    def commit(_value):
        after = deepcopy(component._serialize_fields_document())
        try:
            ComponentCommandService.require().commit_documents(
                component, before, after, description=translate("tween.move_waypoint"),
                edit_key="waypoints", restore_before_execute=True,
            )
        finally:
            component.__dict__.pop("_editor_frozen_draw_points", None)

    def cancel(_value):
        try:
            if component.is_valid and before is not None:
                component._deserialize_fields_document(before)
        finally:
            component.__dict__.pop("_editor_frozen_draw_points", None)

    world = component.world_waypoint(index)
    size = (ctx.world_size(world, 10)
            if component.handles_draw_mode == HandlesDrawMode.ORTHOGRAPHIC
            else component.perspective_handle_size * .15)
    key = f"path-{component.component_id}-{index}"
    callbacks = dict(on_begin=begin, on_commit=commit, on_cancel=cancel)
    ctx.position(key, world, changed, size=size, **callbacks)
    if component.handles_type == HandlesType.FULL:
        for name, axis, color in (
            ("x", (1, 0, 0), (1, .25, .2, 1)),
            ("y", (0, 1, 0), (.3, 1, .3, 1)),
            ("z", (0, 0, 1), (.3, .55, 1, 1)),
        ):
            ctx.position(f"{key}-{name}", world, changed, size=size, axis=axis,
                         length=size * 6, color=color, **callbacks)
    if component.show_indexes or component.show_wp_length:
        text = str(index + 1) if component.show_indexes else ""
        if component.show_wp_length:
            try:
                path = component._drawing_path()
            except ValueError:
                path = None  # Incomplete Bezier groups remain editable.
            distances = path.waypoint_distances if path is not None else ()
            if index < len(distances):
                length = distances[index] - (distances[index - 1] if index else 0)
                text += ("  " if text else "") + f"{length:.2f}"
        if text:
            ctx.label(world, text, color=tuple(component.path_color))


def draw_inspector(ctx, component):
    fields = get_serialized_fields(type(component))
    render_py_component_fields(ctx, component, ("inspector_mode",), render_extra=False)
    mode = component.inspector_mode
    show_tween = mode in (TweenInspectorMode.DEFAULT, TweenInspectorMode.DEVELOPER)
    if show_tween:
        excluded = {"inspector_mode", "waypoints", "drop_to_floor_offset",
                    *_PATH_FIELDS, *_VISUAL_FIELDS}
        names = [name for name, metadata in fields.items()
                 if name not in excluded and not metadata.hidden]
        render_py_component_fields(ctx, component, names, render_extra=False)
    if mode != TweenInspectorMode.INFO_AND_WAYPOINTS_ONLY:
        render_py_component_fields(ctx, component, _PATH_FIELDS, render_extra=False)
        render_py_component_fields(ctx, component, _VISUAL_FIELDS, render_extra=False)
    try:
        path = component._drawing_path()
    except ValueError as error:
        path = None
        ctx.label(str(error))
    ctx.label(translate("tween.path_info").format(
        count=len(component.waypoints), length=0 if path is None else path.length))
    _render_list_field(
        ctx, component, "waypoints", fields["waypoints"], component.waypoints, 140,
        display_name=translate("tween.waypoints"), expanded=component.wps_dropdown,
        on_expanded_change=lambda opened: ComponentCommandService.require().set_field(
            component, "wps_dropdown", opened),
        on_change=lambda _comp, _name, _before, points: set_waypoints(component, points),
    )
    if mode != TweenInspectorMode.INFO_AND_WAYPOINTS_ONLY:
        render_py_component_fields(ctx, component, ("drop_to_floor_offset",), render_extra=False)
        if ctx.button(translate("tween.drop_to_floor")):
            editor.defer(lambda: drop_to_floor(component),
                         description=translate("tween.drop_to_floor"))
    if mode == TweenInspectorMode.DEVELOPER:
        # Native developer mode exposes derived path data for inspection.
        ctx.label(translate("tween.path_baked_info").format(count=len(component.full_wps)))
        ctx.label(f"{component.last_src_position} / {tuple(component.last_src_rotation)}")
    if show_tween:
        draw_events(ctx, component)
