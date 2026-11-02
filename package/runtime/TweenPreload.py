"""Own frame callbacks and the runtime library through plugin unload."""

from infernux.lifecycle import InxPreload
from infernux.timing import Time


class TweenPreload(InxPreload):
    def preload(self, context):
        context.own_python_library("runtime/infernux_tween")
        from infernux_tween import _default_manager, UpdateType
        from infernux.lib._Infernux import _tween_float32

        registrations = {}
        active = {phase: False for phase in (UpdateType.NORMAL, UpdateType.LATE, UpdateType.FIXED)}
        frame_unscaled = 0.0

        def normal(delta):
            nonlocal frame_unscaled
            frame_unscaled = Time.unscaled_delta_time
            if _default_manager.use_smooth_delta_time:
                delta = Time.smooth_delta_time
                frame_unscaled = min(frame_unscaled, _tween_float32(_default_manager.max_smooth_unscaled_time))
            if active[UpdateType.NORMAL]:
                _default_manager._dispatch(delta, frame_unscaled, UpdateType.NORMAL)

        def late(delta):
            if _default_manager.use_smooth_delta_time:
                delta = Time.smooth_delta_time
            _default_manager._dispatch(delta, frame_unscaled, UpdateType.LATE)

        def fixed(delta):
            scale = Time.time_scale
            if scale > 0:
                if _default_manager.use_smooth_delta_time:
                    delta = Time.smooth_delta_time
                _default_manager._dispatch(delta, _tween_float32(delta / scale), UpdateType.FIXED)

        for phase, tick in ((UpdateType.NORMAL, normal), (UpdateType.LATE, late), (UpdateType.FIXED, fixed)):
            registrations[phase] = context.add_update(tick, phase=phase.engine_phase, enabled=False)

        def activity(phase, enabled):
            if phase != UpdateType.MANUAL:
                active[phase] = enabled
                if phase == UpdateType.NORMAL or phase == UpdateType.LATE:
                    # Late consumes the same unscaled sample as Normal, even
                    # when all active animations currently belong to Late.
                    registrations[UpdateType.NORMAL].enabled = active[UpdateType.NORMAL] or active[UpdateType.LATE]
                if phase != UpdateType.NORMAL:
                    registrations[phase].enabled = enabled

        _default_manager._on_activity = activity

        def cleanup():
            _default_manager.clear()
            _default_manager._on_activity = None

        context.add_cleanup(cleanup)
