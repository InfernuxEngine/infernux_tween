"""Shared playback and reversible previews for authored animation components."""

from enum import Enum

from infernux.components import FieldType, InxComponent, serialized_field
from infernux.graph.ramp import AnimationCurve
from infernux.lib import GameObject, SceneManager
from infernux.ui.ui_event import UIEvent

from infernux_tween import (
    _default_manager,
    Ease,
    LoopType,
    Tween,
    TweenManager,
    UpdateType,
)
from infernux_tween.events import TweenCallback, invoke_callbacks


class UpdateClock(Enum):
    AUTO = "Auto"
    NORMAL = "Normal"
    LATE = "Late"
    FIXED = "Fixed"
    MANUAL = "Manual"


def _field_alias(name):
    """Project a public name onto one stored field, without duplicate state."""
    return property(
        lambda self: getattr(self, name), lambda self, value: setattr(self, name, value)
    )


def _event_property(name):
    def assign(self, value):
        if value is not None and not isinstance(value, UIEvent):
            raise TypeError("event must be UIEvent or None")
        bound = self.__dict__.get("_bound_events", {}).get(name)
        previous = self.__dict__.get("_" + name + "_event")
        if bound is not None and bound["event"] is previous:
            bound["entries"] = getattr(self, "on_" + name + "_entries")
        self.__dict__["_" + name + "_event"] = value
        present = set(self._event_objects)
        present.discard(name) if value is None else present.add(name)
        self._event_objects = [event for event in self._event_names if event in present]
        setattr(self, "on_" + name + "_entries", [])

    return property(lambda self: self._event(name), assign)


class TweenAuthoring(InxComponent):
    _event_names = (
        "start",
        "play",
        "update",
        "step_complete",
        "complete",
        "rewind",
        "kill",
        "tween_created",
    )
    target: GameObject = serialized_field(default=None, display_name_key="tween.target")
    duration: float = serialized_field(
        default=1.0, range=(0, 1000), slider=False, display_name_key="tween.duration"
    )
    delay: float = serialized_field(
        default=0.0, range=(0, 1000), slider=False, display_name_key="tween.delay"
    )
    ease: Ease = serialized_field(
        default=Ease.OUT_QUAD,
        display_name_key="tween.ease",
        enum_labels=["tween.ease." + e.name for e in Ease],
        visible_when=lambda c: not c.custom_ease,
    )
    custom_ease: bool = serialized_field(
        default=False, display_name_key="tween.custom_ease"
    )
    curve: AnimationCurve = serialized_field(
        default=AnimationCurve.ease_in_out(0, 0, 1, 1),
        field_type=FieldType.ANIMATION_CURVE,
        display_name_key="tween.curve",
        visible_when=lambda c: c.custom_ease,
    )
    loops: int = serialized_field(default=1, display_name_key="tween.loops")
    loop_type: LoopType = serialized_field(
        default=LoopType.RESTART,
        display_name_key="tween.loop_type",
        enum_labels=["tween.loop." + e.name for e in LoopType],
    )
    clock: UpdateClock = serialized_field(
        default=UpdateClock.AUTO,
        display_name_key="tween.clock",
        enum_labels=["tween.clock." + e.name for e in UpdateClock],
    )
    independent: bool = serialized_field(
        default=False, display_name_key="tween.independent"
    )
    auto_generate: bool = serialized_field(
        default=True, display_name_key="tween.auto_generate"
    )
    auto_play: bool = serialized_field(default=True, display_name_key="tween.auto_play")
    auto_kill: bool = serialized_field(default=True, display_name_key="tween.auto_kill")
    is_speed_based: bool = serialized_field(
        default=False, display_name_key="tween.speed_based"
    )
    tween_id: str = serialized_field(default="", display_name_key="tween.id")
    relative: bool = serialized_field(default=False, display_name_key="tween.relative")
    has_on_start: bool = serialized_field(default=False, hidden=True)
    has_on_play: bool = serialized_field(default=False, hidden=True)
    has_on_update: bool = serialized_field(default=False, hidden=True)
    has_on_step_complete: bool = serialized_field(default=False, hidden=True)
    has_on_complete: bool = serialized_field(default=False, hidden=True)
    has_on_rewind: bool = serialized_field(default=False, hidden=True)
    has_on_tween_created: bool = serialized_field(default=False, hidden=True)
    _event_objects: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.STRING,
        hidden=True,
    )
    on_start_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_complete_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_kill_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_rewind_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_play_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_update_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_step_complete_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    on_tween_created_entries: list = serialized_field(
        default=[],
        field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT,
        element_class=TweenCallback,
        hidden=True,
    )
    _tween = None
    _preview_manager = None
    _preview_registration = None
    _next_animation_index = -1
    _auto_generation_called = False

    ease_type = _field_alias("ease")
    ease_curve = _field_alias("curve")
    id = _field_alias("tween_id")
    is_relative = _field_alias("relative")
    is_independent_update = _field_alias("independent")

    @property
    def update_type(self):
        if self.clock == UpdateClock.AUTO:
            return (
                self._tween.update_type
                if self._tween is not None
                else UpdateType.NORMAL
            )
        return UpdateType[self.clock.name]

    @update_type.setter
    def update_type(self, value):
        if not isinstance(value, UpdateType):
            raise TypeError("update_type must be UpdateType")
        self.clock = UpdateClock[value.name]

    def _event(self, name):
        key = "_" + name + "_event"
        if key not in self.__dict__ and (
            name == "kill"
            or name in self._event_objects
            or getattr(self, "on_" + name + "_entries")
        ):
            self.__dict__[key] = UIEvent()
        return self.__dict__.get(key)

    on_start = _event_property("start")
    on_play = _event_property("play")
    on_update = _event_property("update")
    on_step_complete = _event_property("step_complete")
    on_complete = _event_property("complete")
    on_rewind = _event_property("rewind")
    on_tween_created = _event_property("tween_created")

    @property
    def on_kill(self):
        return self._event("kill")

    def _invoke_event(self, name, event=None, entries=None):
        event = getattr(self, "on_" + name) if event is None else event
        if event is not None:
            event.invoke()
        if not self.is_valid:
            return
        bindings = self.__dict__.setdefault("_persistent_events", {}).setdefault(
            name, []
        )
        invoke_callbacks(
            getattr(self, "on_" + name + "_entries") if entries is None else entries,
            bindings,
            self,
        )

    def _invoke_bound_event(self, name, bound):
        if self.__dict__.get("_" + name + "_event") is bound["event"]:
            bound["entries"] = getattr(self, "on_" + name + "_entries")
        self._invoke_event(name, bound["event"], bound["entries"])

    def on_validate(self):
        self.__dict__.pop("_persistent_events", None)

    def _deserialize_fields_document(self, data, **kwargs):
        # Active delegates keep their captured event. The restored public
        # fields get fresh objects, with only authored listeners restored.
        for name, bound in self.__dict__.get("_bound_events", {}).items():
            if self.__dict__.get("_" + name + "_event") is bound["event"]:
                bound["entries"] = getattr(self, "on_" + name + "_entries")
        result = super()._deserialize_fields_document(data, **kwargs)
        for name in self._event_names:
            self.__dict__.pop("_" + name + "_event", None)
        self.__dict__.pop("_persistent_events", None)
        return result

    def on_disable(self):
        self.__dict__.pop("_persistent_events", None)

    def _target_object(self):
        return self.game_object if self.target is None else self.target

    def _lifetime_target(self):
        return self._target_object()

    def on_enable(self):
        if (
            self.auto_generate
            and SceneManager.instance().is_playing()
            and not self._auto_generation_called
        ):
            self._auto_generation_called = True
            self.create_tween(and_play=self.auto_play)

    def on_destroy(self):
        try:
            if self._tween is not None:
                self._tween.kill()
        finally:
            self.__dict__.pop("_persistent_events", None)

    def _build(self, preview=False):
        raise NotImplementedError

    def _capture_preview(self, scope):
        raise NotImplementedError

    def _after_configure(self, tween):
        pass

    def _configure_relative(self, tween):
        tween.set_relative(self.relative)

    def _group_target(self):
        return self._target_object()

    def create_tween(
        self, regenerate_if_exists: bool = False, and_play: bool = True
    ) -> None:
        self._create_tween(regenerate_if_exists, and_play)

    def _create_tween(
        self, regenerate_if_exists=False, and_play=True, *, preview=False
    ):
        if (
            self._tween is not None
            and self._tween.is_active()
            and not regenerate_if_exists
        ):
            return self._tween
        if self._tween is not None:
            self._tween.kill()
        tween = self._build(preview)
        if tween is None:
            self._tween = None
            return None
        try:
            tween.set_delay(self.delay).set_ease(
                self.curve if self.custom_ease else self.ease
            ).set_loops(self.loops, self.loop_type)
            self._configure_relative(tween)
            tween.set_auto_kill(
                False if preview else self.auto_kill
            )
            tween.set_speed_based(self.is_speed_based)
            tween.set_target(self._group_target())
            if self.tween_id:
                tween.set_id(self.tween_id)
            if preview:
                tween.set_update(UpdateType.MANUAL)
            else:
                phase = (
                    tween.update_type
                    if self.clock == UpdateClock.AUTO
                    else UpdateType[self.clock.name]
                )
                tween.set_update(phase, self.independent)
                for name in self._event_names[:-1]:
                    if name == "kill":
                        continue
                    if not getattr(self, "has_on_" + name):
                        setattr(self, "on_" + name, None)
                        continue
                    event = getattr(self, "on_" + name)
                    entries = getattr(self, "on_" + name + "_entries")
                    if event is not None:
                        bound = {"event": event, "entries": entries}
                        self.__dict__.setdefault("_bound_events", {})[name] = bound
                        getattr(tween, "on_" + name)(
                            lambda name=name, bound=bound: self._invoke_bound_event(
                                name, bound
                            )
                        )

                def killed():
                    self._invoke_event("kill")
                    if self._tween is tween:
                        self._tween = None
                        self.__dict__.pop("_bound_events", None)

                tween.on_kill(killed)
                if SceneManager.instance().is_playing():
                    tween.set_link(self._lifetime_target())
            self._after_configure(tween)
        except BaseException:
            tween.kill()
            raise
        self._tween = tween
        if not and_play:
            tween.pause()
        if not preview and self.has_on_tween_created:
            self._invoke_event("tween_created")
        return tween

    def recreate_tween(self) -> None:
        self.create_tween(True, False)

    def recreate_tween_and_play(self) -> None:
        self.create_tween(True, True)

    def rewind_then_recreate_tween(self) -> None:
        self.twn_rewind()
        self.recreate_tween()

    def rewind_then_recreate_tween_and_play(self) -> None:
        self.twn_rewind()
        self.recreate_tween_and_play()

    def create_editor_preview(self):
        return self._create_tween(True, False, preview=True)

    @property
    def tween(self) -> Tween | None:
        return self._tween

    @tween.setter
    def tween(self, value: Tween | None):
        self._tween = value

    def get_tweens(self):
        return [
            component._tween
            for component in self.game_object.get_components(type(self))
            if component._tween is not None and component._tween.is_active()
        ]

    def _control_tweens(self, tweens, method, *args):
        for tween in tuple(tweens or ()):
            getattr(tween, method)(*args)
        self._sync_preview()

    def _control(self, method, *args):
        if self._preview_manager is not None:
            tweens = [self._tween] if self._tween is not None else []
        else:
            tweens = _default_manager.tweens_by_target(self._group_target())
        self._control_tweens(tweens, method, *args)

    def _control_by_id(self, method, id: str, *, all_targets=False):
        tweens = _default_manager.tweens_by_id(id)
        if not all_targets and tweens:
            target = self._group_target()
            tweens = [tween for tween in tweens if tween.target is target]
        self._control_tweens(tweens, method)

    def twn_play(self) -> None:
        self._control("play")

    def twn_play_forward(self) -> None:
        self._control("play_forward")

    def twn_play_backwards(self) -> None:
        self._control("play_backwards")

    def twn_pause(self) -> None:
        self._control("pause")

    def twn_toggle_pause(self) -> None:
        self._control("toggle_pause")

    def twn_complete(self) -> None:
        self._control("complete")

    def twn_kill(self) -> None:
        self._control("kill")

    def twn_goto_and_pause(self, time: float) -> None:
        self._control("goto", time, False)

    def twn_goto_and_play(self, time: float) -> None:
        self._control("goto", time, True)

    def twn_rewind(self) -> None:
        self._next_animation_index = -1
        animations = self.game_object.get_components(type(self))
        for component in reversed(animations):
            tween = component._tween
            if tween is not None and tween.is_initialized():
                tween.rewind()
                component._sync_preview()

    def _restart_from_here(self):
        pass

    def twn_restart(self, from_here: bool = False) -> None:
        if self._tween is not None and self._tween.is_active():
            self._next_animation_index = -1
            if from_here and self.relative:
                self._restart_from_here()
            self._control("restart")

    def twn_play_by_id(self, id: str) -> None:
        self._control_by_id("play", id)

    def twn_play_all_by_id(self, id: str) -> None:
        self._control_by_id("play", id, all_targets=True)

    def twn_pause_all_by_id(self, id: str) -> None:
        self._control_by_id("pause", id, all_targets=True)

    def twn_play_backwards_by_id(self, id: str) -> None:
        self._control_by_id("play_backwards", id)

    def twn_play_backwards_all_by_id(self, id: str) -> None:
        self._control_by_id("play_backwards", id, all_targets=True)

    def twn_play_forward_by_id(self, id: str) -> None:
        self._control_by_id("play_forward", id)

    def twn_play_forward_all_by_id(self, id: str) -> None:
        self._control_by_id("play_forward", id, all_targets=True)

    def twn_kill_by_id(self, id: str) -> None:
        self._control_by_id("kill", id)

    def twn_kill_all_by_id(self, id: str) -> None:
        self._control_by_id("kill", id, all_targets=True)

    def twn_rewind_all_by_id(self, id: str) -> None:
        self._next_animation_index = -1
        self._control_by_id("rewind", id, all_targets=True)

    def twn_restart_by_id(self, id: str) -> None:
        self._next_animation_index = -1
        self._control_by_id("restart", id)

    def twn_restart_all_by_id(self, id: str) -> None:
        self._next_animation_index = -1
        self._control_by_id("restart", id, all_targets=True)

    def twn_play_next(self) -> None:
        animations = self.game_object.get_components(type(self))
        for index in range(self._next_animation_index + 1, len(animations)):
            self._next_animation_index = index
            tween = animations[index]._tween
            if (
                tween is not None
                and tween.is_active()
                and not tween.is_playing()
                and not tween.is_complete()
            ):
                tween.play()
                break

    def twn_rewind_and_play_next(self) -> None:
        self._next_animation_index = -1
        self._control("rewind")
        self.twn_play_next()

    @property
    def _preview_tween(self):
        return self.__dict__.get("_preview_owned_tween")

    @_preview_tween.setter
    def _preview_tween(self, value):
        previous = self._preview_tween
        if previous is not None and previous is not value:
            previous.kill()
        self.__dict__["_preview_owned_tween"] = value

    def _sync_preview(self):
        if self._preview_registration is not None:
            self._preview_registration.enabled = (
                self._tween is not None and self._tween.is_playing()
            )

    def begin_preview(self, scope):
        scope.capture(
            self,
            "_tween",
            "_preview_manager",
            "_preview_registration",
            "_preview_tween",
        )
        self._capture_preview(scope)
        tween = self._create_tween(True, preview=True)
        if tween is None:
            return None
        _default_manager._remove(tween)
        self._preview_manager = TweenManager()
        self._preview_manager.add(tween)
        self._preview_tween = tween

        def tick(delta):
            self._preview_manager.manual_update(delta, delta)
            self._sync_preview()

        self._preview_registration = scope.add_update(tick)
        return tween
