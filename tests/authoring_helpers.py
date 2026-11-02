from infernux.ui.ui_event import UIEvent


def add_animation(obj):
    """An explicitly configured local-movement fixture."""
    from runtime.TweenAnimation import AnimationType, TargetType, TweenAnimation

    component = obj.add_component(TweenAnimation)
    component.animation_type = AnimationType.LOCAL_MOVE
    component.animation_valid = True
    component.target = obj.transform
    component.target_type = TargetType.TRANSFORM
    component.end_vector = (0.0, 1.0, 0.0)
    component.end_size = (100.0, 40.0)
    component.end_value = 1.0
    component.optional_bool1 = True
    component.optional_int0 = 10
    component.optional_float0 = 1.0
    return component


def subscribe(component, name, callback):
    if name != "kill":
        setattr(component, "has_on_" + name, True)
    if getattr(component, "on_" + name) is None:
        setattr(component, "on_" + name, UIEvent())
    getattr(component, "on_" + name).add_listener(callback)
