"""Serialized component callbacks using the engine's event argument binding."""
from infernux.components import ComponentRef, FieldType, SerializableObject, serialized_field
from infernux.debug import Debug
from infernux.ui.ui_event_entry import UIEventArgument, _UIEventRuntimeBinding, _get_serializable_raw_field


class TweenCallback(SerializableObject):
    target = serialized_field(default=ComponentRef(), field_type=FieldType.COMPONENT,
                              display_name_key="tween.callback_target")
    method_name: str = serialized_field(default="", display_name_key="tween.callback_method")
    arguments: list = serialized_field(default=[], field_type=FieldType.LIST,
                                      element_type=FieldType.SERIALIZABLE_OBJECT, element_class=UIEventArgument)

    @property
    def component_name(self):
        return _get_serializable_raw_field(self, "target").component_type


def invoke_callbacks(entries, bindings, owner):
    entries = tuple(entries)
    del bindings[len(entries):]
    bindings.extend([None] * (len(entries)-len(bindings)))
    for index, entry in enumerate(entries):
        reference = _get_serializable_raw_field(entry, "target")
        if not reference.go_id or not entry.method_name:
            bindings[index] = None
            continue
        component = entry.target
        if component is None:
            bindings[index] = None
            Debug.log_error(f"Tween callback target is unavailable: {entry.method_name}", owner)
            continue
        target = component.game_object
        binding = bindings[index]
        if binding is None or not binding.matches(entry, target, component):
            binding = bindings[index] = _UIEventRuntimeBinding.create(entry, component, target)
        result = binding.invoke(entry)
        if result.status not in {"resolved", "direct"}:
            bindings[index] = None
            Debug.log_error(f"Tween callback {entry.method_name}: {result.message}", owner)
