"""Shared playback and reversible previews for authored animation components."""
from enum import Enum

from infernux.components import FieldType, InxComponent, serialized_field
from infernux.graph.ramp import AnimationCurve
from infernux.lib import GameObject, SceneManager
from infernux.ui.ui_event import UIEvent

from infernux_tween import _default_manager, Ease, LoopType, TweenManager, UpdateType
from infernux_tween.events import TweenCallback, invoke_callbacks


class UpdateClock(Enum):
    AUTO = "Auto"
    NORMAL = "Normal"
    LATE = "Late"
    FIXED = "Fixed"
    MANUAL = "Manual"


class TweenAuthoring(InxComponent):
    _event_names = ('start', 'play', 'update', 'step_complete', 'complete', 'rewind', 'kill', 'tween_created')
    target: GameObject = serialized_field(default=None, display_name_key="tween.target")
    duration: float = serialized_field(default=1.0, range=(0, 1000), slider=False, display_name_key="tween.duration")
    delay: float = serialized_field(default=0.0, range=(0, 1000), slider=False, display_name_key="tween.delay")
    ease: Ease = serialized_field(default=Ease.OUT_QUAD, display_name_key="tween.ease", enum_labels=["tween.ease."+e.name for e in Ease],
                                 visible_when=lambda c: not c.custom_ease)
    custom_ease: bool = serialized_field(default=False, display_name_key="tween.custom_ease")
    curve: AnimationCurve = serialized_field(default=AnimationCurve(), field_type=FieldType.ANIMATION_CURVE,
                                              display_name_key="tween.curve", visible_when=lambda c: c.custom_ease)
    loops: int = serialized_field(default=1, display_name_key="tween.loops")
    loop_type: LoopType = serialized_field(default=LoopType.RESTART, display_name_key="tween.loop_type", enum_labels=["tween.loop."+e.name for e in LoopType])
    clock: UpdateClock = serialized_field(default=UpdateClock.AUTO, display_name_key="tween.clock", enum_labels=["tween.clock."+e.name for e in UpdateClock])
    independent: bool = serialized_field(default=False, display_name_key="tween.independent")
    auto_play: bool = serialized_field(default=True, display_name_key="tween.auto_play")
    auto_kill: bool = serialized_field(default=True, display_name_key="tween.auto_kill")
    tween_id: str = serialized_field(default="", display_name_key="tween.id")
    relative: bool = serialized_field(default=False, display_name_key="tween.relative")
    on_start_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_complete_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_kill_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_rewind_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_play_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_update_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_step_complete_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    on_tween_created_entries: list = serialized_field(default=[], field_type=FieldType.LIST,
        element_type=FieldType.SERIALIZABLE_OBJECT, element_class=TweenCallback, hidden=True)
    _tween = None
    _preview_manager = None
    _preview_registration = None
    _next_animation_index = -1

    def _event(self, name):
        if name not in self.__dict__:
            self.__dict__[name] = UIEvent()
        return self.__dict__[name]

    @property
    def on_start(self): return self._event("_start_event")
    @property
    def on_complete(self): return self._event("_complete_event")
    @property
    def on_kill(self): return self._event("_kill_event")
    @property
    def on_rewind(self): return self._event("_rewind_event")
    @property
    def on_play(self): return self._event("_play_event")
    @property
    def on_update(self): return self._event("_update_event")
    @property
    def on_step_complete(self): return self._event("_step_complete_event")
    @property
    def on_tween_created(self): return self._event("_tween_created_event")

    def _invoke_event(self, name):
        getattr(self, "on_"+name).invoke()
        if not self.is_valid:
            return
        bindings = self.__dict__.setdefault("_persistent_events", {}).setdefault(name, [])
        invoke_callbacks(getattr(self, "on_"+name+"_entries"), bindings, self)

    def on_validate(self):
        self.__dict__.pop("_persistent_events", None)

    def on_disable(self):
        self.__dict__.pop("_persistent_events", None)

    def _target_object(self):
        return self.game_object if self.target is None else self.target

    def _lifetime_target(self):
        return self._target_object()

    def on_enable(self):
        if SceneManager.instance().is_playing() and self._tween is None:
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

    def _group_target(self):
        return self._target_object()

    def create_tween(self, regenerate_if_exists: bool=False, and_play: bool=True) -> None:
        self._create_tween(regenerate_if_exists, and_play)

    def _create_tween(self, regenerate_if_exists=False, and_play=True, *, preview=False):
        if self._tween is not None and self._tween.is_active() and not regenerate_if_exists:
            return self._tween
        if self._tween is not None:
            self._tween.kill()
        tween = self._build(preview)
        if tween is None:
            self._tween = None
            raise ValueError("The selected target has no matching animatable property")
        try:
            tween.set_delay(self.delay).set_ease(self.curve if self.custom_ease else self.ease).set_loops(self.loops, self.loop_type)
            tween.set_relative(self.relative).set_auto_kill(False if preview else self.auto_kill)
            tween.set_target(self._group_target())
            if self.tween_id:
                tween.set_id(self.tween_id)
            if preview:
                tween.set_update(UpdateType.MANUAL)
            else:
                phase = tween.update_type if self.clock == UpdateClock.AUTO else UpdateType[self.clock.name]
                tween.set_update(phase, self.independent)
                for name in self._event_names[:-1]:
                    getattr(tween, 'on_' + name)(lambda name=name: self._invoke_event(name))
                if SceneManager.instance().is_playing():
                    tween.set_link(self._lifetime_target())
            self._after_configure(tween)
        except BaseException:
            tween.kill()
            raise
        self._tween = tween
        if not and_play:
            tween.pause()
        if not preview:
            self._invoke_event('tween_created')
        return tween

    def recreate_tween(self) -> None:
        self.create_tween(True, False)

    def recreate_tween_and_play(self) -> None:
        self.create_tween(True, True)

    def rewind_then_recreate_tween(self) -> None:
        self.do_rewind()
        self.recreate_tween()

    def rewind_then_recreate_tween_and_play(self) -> None:
        self.do_rewind()
        self.recreate_tween_and_play()

    def create_editor_preview(self):
        return self._create_tween(True, False, preview=True)

    def get_tween(self): return self._tween

    def get_tweens(self):
        return [component._tween for component in self.game_object.get_components(type(self))
                if component._tween is not None and component._tween.is_active()]

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

    def do_play(self) -> None: self._control('play')
    def do_play_forward(self) -> None: self._control('play_forward')
    def do_play_backwards(self) -> None: self._control('play_backwards')
    def do_pause(self) -> None: self._control('pause')
    def do_toggle_pause(self) -> None: self._control('toggle_pause')
    def do_complete(self) -> None: self._control('complete')
    def do_kill(self) -> None: self._control('kill')
    def do_goto_and_pause(self, time: float) -> None: self._control('goto', time, False)
    def do_goto_and_play(self, time: float) -> None: self._control('goto', time, True)

    def do_rewind(self) -> None:
        self._next_animation_index = -1
        animations = self.game_object.get_components(type(self))
        for component in reversed(animations):
            tween = component._tween
            if tween is not None and tween.is_initialized():
                tween.rewind()
                component._sync_preview()

    def _restart_from_here(self):
        pass

    def do_restart(self, from_here: bool=False) -> None:
        if self._tween is not None and self._tween.is_active():
            self._next_animation_index = -1
            if from_here and self.relative:
                self._restart_from_here()
            self._control('restart')

    def do_play_by_id(self, id: str) -> None: self._control_by_id('play', id)
    def do_play_all_by_id(self, id: str) -> None: self._control_by_id('play', id, all_targets=True)
    def do_pause_all_by_id(self, id: str) -> None: self._control_by_id('pause', id, all_targets=True)
    def do_play_backwards_by_id(self, id: str) -> None: self._control_by_id('play_backwards', id)
    def do_play_backwards_all_by_id(self, id: str) -> None: self._control_by_id('play_backwards', id, all_targets=True)
    def do_play_forward_by_id(self, id: str) -> None: self._control_by_id('play_forward', id)
    def do_play_forward_all_by_id(self, id: str) -> None: self._control_by_id('play_forward', id, all_targets=True)
    def do_kill_by_id(self, id: str) -> None: self._control_by_id('kill', id)
    def do_kill_all_by_id(self, id: str) -> None: self._control_by_id('kill', id, all_targets=True)

    def do_rewind_all_by_id(self, id: str) -> None:
        self._next_animation_index = -1
        self._control_by_id('rewind', id, all_targets=True)

    def do_restart_by_id(self, id: str) -> None:
        self._next_animation_index = -1
        self._control_by_id('restart', id)

    def do_restart_all_by_id(self, id: str) -> None:
        self._next_animation_index = -1
        self._control_by_id('restart', id, all_targets=True)

    def do_play_next(self) -> None:
        animations = self.game_object.get_components(type(self))
        for index in range(self._next_animation_index + 1, len(animations)):
            self._next_animation_index = index
            tween = animations[index]._tween
            if tween is not None and tween.is_active() and not tween.is_playing() and not tween.is_complete():
                tween.play()
                break

    def do_rewind_and_play_next(self) -> None:
        self._next_animation_index = -1
        self._control('rewind')
        self.do_play_next()

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
            self._preview_registration.enabled = self._tween is not None and self._tween.is_playing()

    def begin_preview(self, scope):
        scope.capture(self, "_tween", "_preview_manager", "_preview_registration", "_preview_tween")
        self._capture_preview(scope)
        tween = self._create_tween(True, preview=True)
        _default_manager._remove(tween)
        self._preview_manager = TweenManager()
        self._preview_manager.add(tween)
        self._preview_tween = tween

        def tick(delta):
            self._preview_manager.manual_update(delta, delta)
            self._sync_preview()

        self._preview_registration = scope.add_update(tick)
        return tween
