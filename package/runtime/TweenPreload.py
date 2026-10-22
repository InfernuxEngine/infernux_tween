"""Own frame callbacks and the runtime library through plugin unload."""

from infernux.lifecycle import InxPreload
from infernux.timing import Time


class TweenPreload(InxPreload):
    def preload(self, context):
        from infernux.lib import TextLayout

        if not hasattr(TextLayout, "split_graphemes"):
            raise RuntimeError("Tween requires Infernux 0.4.3 build 3 or later")
        context.own_python_library("runtime/infernux_tween")
        from infernux_tween import DOTween, UpdateType

        registrations = {}
        for phase in (UpdateType.Normal, UpdateType.Late, UpdateType.Fixed):
            def tick(delta, phase=phase):
                unscaled = delta / Time.time_scale if phase == UpdateType.Fixed else Time.unscaled_delta_time
                DOTween.Update(delta, unscaled, phase)
            registrations[phase] = context.add_update(tick, phase=phase.value, enabled=False)

        def activity(phase, enabled):
            if phase != UpdateType.Manual:
                registrations[phase].enabled = enabled

        DOTween._on_activity = activity

        def cleanup():
            DOTween.Clear()
            DOTween._on_activity = None

        context.add_cleanup(cleanup)
