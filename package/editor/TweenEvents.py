"""Persistent Tween callbacks with the engine's list, reference and Undo widgets."""
from copy import deepcopy
from functools import lru_cache
import inspect
import types
from typing import Union, get_args, get_origin, get_type_hints

from infernux.components import ComponentRef, FieldType, get_serialized_fields
from infernux.components.fields import get_raw_field_value
from infernux.editor import translate
from infernux.engine.interaction.components import ComponentCommandService
from infernux.engine.runtime_dispatch import current_runtime_epoch
from infernux.engine.ui.igui import IGUI
from infernux.engine.ui.inspector_components import render_object_field
from infernux.engine.ui._inspector_references import (
    _picker_scene_components, _create_reference_value_from_payload,
    _picker_scene_gameobjects, _get_reference_display_name,
)
from infernux.engine.ui.inspector_utils import field_label, max_label_w, render_compact_section_header, render_serialized_field
from infernux.ui.ui_event_entry import UIEventArgument, get_callable_methods, get_method_parameter_specs, normalize_event_arguments

from infernux_tween.events import TweenCallback


def _supported_parameter(annotation, default):
    if get_origin(annotation) in (Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) != 1:
            return False
        annotation = args[0]
    if annotation is inspect.Parameter.empty:
        annotation = type(default) if default is not inspect.Parameter.empty else None
    if annotation in (bool, int, float, str):
        return True
    from infernux.components import GameObjectRef, InxComponent
    from infernux.components.builtin_component import BuiltinComponent
    from infernux.lib import GameObject
    return (annotation in (GameObject, GameObjectRef, ComponentRef)
            or isinstance(annotation, type) and issubclass(annotation, (InxComponent, BuiltinComponent)))


@lru_cache(maxsize=128)
def _cached_methods(component_type, epoch):
    names = []
    for name in get_callable_methods(component_type):
        try:
            method = getattr(component_type, name)
            signature = inspect.signature(method)
            hints = get_type_hints(method)
            get_method_parameter_specs(component_type, name)
        except (TypeError, ValueError, NameError):
            continue
        parameters = [p for p in signature.parameters.values() if p.name not in ('self', 'cls')]
        if all(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
               and _supported_parameter(hints.get(p.name, p.annotation), p.default) for p in parameters):
            names.append(name)
    return names


def _methods(component_type):
    return _cached_methods(component_type, current_runtime_epoch().epoch_id)


def _edit(component, field, mutate):
    entries = deepcopy(getattr(component, field))
    mutate(entries)
    ComponentCommandService.require().set_field(component, field, entries, description=translate('tween.edit_events'))


def _reference(ctx, component, wid, label, value, kind, setter, label_width, component_type=''):
    scene = component.game_object.scene

    def accept(payload):
        reference = _create_reference_value_from_payload(kind, payload, component_type, scene=scene)
        if reference is not None:
            setter(reference)

    field_label(ctx, label, label_width)
    render_object_field(ctx, wid, _get_reference_display_name(kind, value), component_type or ('Component' if kind == FieldType.COMPONENT else 'GameObject'),
        accept_drag_type='HIERARCHY_GAMEOBJECT', on_drop_callback=accept, on_pick=accept,
        picker_scene_items=(lambda query: _picker_scene_components(query, component_type, scene=scene))
            if kind == FieldType.COMPONENT else (lambda query: _picker_scene_gameobjects(query, scene=scene)),
        on_clear=lambda: setter(ComponentRef() if kind == FieldType.COMPONENT else None),
        semantic_id=f"inspector.object.{component.game_object.id}.component.{component.component_id}.{wid}")


def _entry(ctx, component, field, index, entry, label_width):
    def target_changed(value):
        def change(entries):
            item = entries[index]
            item.target, item.method_name, item.arguments = value, '', []
        _edit(component, field, change)

    reference = get_raw_field_value(entry, 'target')
    _reference(ctx, component, f'{field}.{index}.target', translate('tween.callback_target'), reference,
               FieldType.COMPONENT, target_changed, label_width)
    target = entry.target
    if target is None:
        return
    names = [''] + _methods(type(target))
    selected = names.index(entry.method_name) if entry.method_name in names else 0
    field_label(ctx, translate('tween.callback_method'), label_width)
    choice = ctx.combo(f'##{field}.{index}.method', selected, [translate('tween.no_function')] + names[1:], -1)
    if choice != selected:
        name = names[choice]
        arguments = normalize_event_arguments(entry.arguments, get_method_parameter_specs(target, name)) if name else []
        def changed(entries):
            entries[index].method_name, entries[index].arguments = name, arguments
        _edit(component, field, changed)
    if entry.method_name and entry.method_name not in names:
        ctx.label(translate('tween.missing_method').format(name=entry.method_name))
    fields = get_serialized_fields(UIEventArgument)
    for arg_index, argument in enumerate(entry.arguments):
        ctx.push_id(arg_index)
        try:
            key = {'int': 'int_value', 'float': 'float_value', 'bool': 'bool_value',
                   'str': 'string_value', 'string': 'string_value', 'game_object': 'game_object', 'component': 'component'}[argument.kind]
            value = get_raw_field_value(argument, key)
            def argument_changed(updated, arg_index=arg_index, key=key):
                _edit(component, field, lambda entries: setattr(entries[index].arguments[arg_index], key, updated))
            if key in {'component', 'game_object'}:
                _reference(ctx, component, f'{field}.{index}.arguments.{arg_index}', argument.name, value,
                           fields[key].field_type, argument_changed, label_width, argument.component_type)
            else:
                updated = render_serialized_field(ctx, '##argument', argument.name, fields[key], value, label_width)
                if updated != value:
                    argument_changed(updated)
        finally:
            ctx.pop_id()


def draw_events(ctx, component):
    label_width = max_label_w(ctx, [translate('tween.callback_target'), translate('tween.callback_method')])
    for name in component._event_names:
        field = 'on_'+name+'_entries'
        ctx.push_id_str(field)
        try:
            entries = getattr(component, field)
            if not IGUI.list_header(ctx, translate('tween.on_'+name), len(entries),
                    on_add=lambda field=field: _edit(component, field, lambda items: items.append(TweenCallback())), level='primary'):
                continue
            for index, entry in enumerate(entries):
                ctx.push_id(index)
                try:
                    expanded = render_compact_section_header(ctx, translate('tween.callback_entry').format(n=index+1),
                                                              level='tertiary', allow_overlap=True)
                    ctx.same_line(0, 0)
                    ctx.set_cursor_pos_x(ctx.get_cursor_pos_x()+max(0, ctx.get_content_region_avail_width()-24))
                    if IGUI.list_item_remove_button(ctx, 'callback'):
                        _edit(component, field, lambda items, index=index: items.pop(index))
                        break
                    if expanded:
                        _entry(ctx, component, field, index, entry, label_width)
                finally:
                    ctx.pop_id()
        finally:
            ctx.pop_id()
