"""Shared playback and reversible previews for authored animation components."""
from enum import Enum

from infernux.components import FieldType, InxComponent, serialized_field
from infernux.graph.ramp import AnimationCurve
from infernux.lib import GameObject, SceneManager
from infernux.ui.ui_event import UIEvent

from infernux_tween import DOTween, Ease, LoopType, TweenManager, UpdateType


class UpdateClock(str, Enum):
    Auto = "Auto"
    Normal = "Normal"
    Late = "Late"
    Fixed = "Fixed"
    Manual = "Manual"


class TweenAuthoring(InxComponent):
    target: GameObject = serialized_field(default=None, display_name_key="tween.target")
    duration: float = serialized_field(default=1.0, range=(0, 1000), slider=False, display_name_key="tween.duration")
    delay: float = serialized_field(default=0.0, range=(0, 1000), slider=False, display_name_key="tween.delay")
    ease: Ease = serialized_field(default=Ease.OutQuad, display_name_key="tween.ease", enum_labels=["tween.ease."+e.name for e in Ease],
                                 visible_when=lambda c: not c.custom_ease)
    custom_ease: bool = serialized_field(default=False, display_name_key="tween.custom_ease")
    curve: AnimationCurve = serialized_field(default=AnimationCurve(), field_type=FieldType.ANIMATION_CURVE,
                                              display_name_key="tween.curve", visible_when=lambda c: c.custom_ease)
    loops: int = serialized_field(default=1, display_name_key="tween.loops")
    loop_type: LoopType = serialized_field(default=LoopType.Restart, display_name_key="tween.loop_type", enum_labels=["tween.loop."+e.name for e in LoopType])
    clock: UpdateClock = serialized_field(default=UpdateClock.Auto, display_name_key="tween.clock", enum_labels=["tween.clock."+e.name for e in UpdateClock])
    independent: bool = serialized_field(default=False, display_name_key="tween.independent")
    auto_play: bool = serialized_field(default=True, display_name_key="tween.auto_play")
    auto_kill: bool = serialized_field(default=False, display_name_key="tween.auto_kill")
    tween_id: str = serialized_field(default="", display_name_key="tween.id")
    relative: bool = serialized_field(default=False, display_name_key="tween.relative")
    _tween = None
    _preview_manager = None
    _preview_registration = None

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

    def _target_object(self):
        return self.game_object if self.target is None else self.target

    def _lifetime_target(self):
        return self._target_object()

    def on_enable(self):
        if SceneManager.instance().is_playing() and self._tween is None:
            self.CreateTween()

    def on_destroy(self):
        if self._tween is not None:
            self._tween.Kill()

    def _build(self, preview=False):
        raise NotImplementedError

    def _capture_preview(self, scope):
        raise NotImplementedError

    def _after_configure(self, tween):
        pass

    def CreateTween(self, recreate=False, *, preview=False):
        if self._tween is not None and self._tween.IsActive() and not recreate:
            return self._tween
        if self._tween is not None:
            self._tween.Kill()
        tween = self._build(preview)
        try:
            tween.SetDelay(self.delay).SetEase(self.curve if self.custom_ease else self.ease).SetLoops(self.loops, self.loop_type)
            tween.SetRelative(self.relative).SetAutoKill(False if preview else self.auto_kill)
            if self.tween_id:
                tween.SetId(self.tween_id)
            if preview:
                tween.SetUpdate(UpdateType.Manual)
            else:
                phase = tween.update_type if self.clock == UpdateClock.Auto else UpdateType[self.clock.name]
                tween.SetUpdate(phase, self.independent)
                tween.OnStart(self.on_start.invoke).OnComplete(self.on_complete.invoke)
                tween.OnKill(self.on_kill.invoke).OnRewind(self.on_rewind.invoke)
                if SceneManager.instance().is_playing():
                    tween.SetLink(self._lifetime_target())
            self._after_configure(tween)
        except BaseException:
            tween.Kill()
            raise
        self._tween = tween
        if not self.auto_play and not preview:
            tween.Pause()
        return tween

    def GetTween(self): return self._tween

    def GetTweens(self):
        return [component._tween for component in self.game_object.get_components(TweenAuthoring)
                if component._tween is not None and component._tween.IsActive()]

    def _control(self, method, *args):
        if self._tween is not None:
            getattr(self._tween, method)(*args)
            self._sync_preview()
        return self

    def DOPlay(self): return self._control("Play")
    def DOPlayForward(self): return self._control("PlayForward")
    def DOPlayBackwards(self): return self._control("PlayBackwards")
    def DOPause(self): return self._control("Pause")
    def DOTogglePause(self): return self._control("TogglePause")
    def DORewind(self): return self._control("Rewind")
    def DOComplete(self, with_callbacks=False): return self._control("Complete", with_callbacks)
    def DOKill(self, complete=False): return self._control("Kill", complete)

    def DORestart(self):
        if self._tween is None or not self._tween.IsActive():
            self.CreateTween(recreate=True)
        return self._control("Restart")

    @property
    def _preview_tween(self):
        return self.__dict__.get("_preview_owned_tween")

    @_preview_tween.setter
    def _preview_tween(self, value):
        previous = self._preview_tween
        if previous is not None and previous is not value:
            previous.Kill()
        self.__dict__["_preview_owned_tween"] = value

    def _sync_preview(self):
        if self._preview_registration is not None:
            self._preview_registration.enabled = self._tween is not None and self._tween.IsPlaying()

    def BeginPreview(self, scope):
        scope.capture(self, "_tween", "_preview_manager", "_preview_registration", "_preview_tween")
        self._capture_preview(scope)
        tween = self.CreateTween(recreate=True, preview=True)
        DOTween._remove(tween)
        self._preview_manager = TweenManager()
        self._preview_manager.add(tween)
        self._preview_tween = tween

        def tick(delta):
            self._preview_manager.ManualUpdate(delta, delta)
            self._sync_preview()

        self._preview_registration = scope.add_update(tick)
        return tween
