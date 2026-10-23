"""Own frame callbacks and the runtime library through plugin unload."""

from infernux.lifecycle import InxPreload
from infernux.timing import Time


class TweenPreload(InxPreload):
    def preload(self, context):
        from infernux.lib import TextCharacterBuffer

        if not hasattr(TextCharacterBuffer, "color_overrides"):
            raise RuntimeError("Tween requires Infernux 0.4.3 hotfix 4 or later")
        context.own_python_library("runtime/infernux_tween")
        from infernux_tween import _default_manager, UpdateType

        registrations = {}
        for phase in (UpdateType.NORMAL, UpdateType.LATE, UpdateType.FIXED):
            def tick(delta, phase=phase):
                unscaled = delta / Time.time_scale if phase == UpdateType.FIXED else Time.unscaled_delta_time
                _default_manager.update(delta, unscaled, phase)
            registrations[phase] = context.add_update(tick, phase=phase.value, enabled=False)

        def activity(phase, enabled):
            if phase != UpdateType.MANUAL:
                registrations[phase].enabled = enabled

        _default_manager._on_activity = activity

        def cleanup():
            _default_manager.clear()
            _default_manager._on_activity = None

        context.add_cleanup(cleanup)
