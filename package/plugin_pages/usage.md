# Tween

Paths use `ShortcutExtensions.DOPath(transform, points, seconds, PathType.CatmullRom)`.
Choose `Ease.Linear` for constant arc-length motion. `SetSpeedBased()` treats
the duration argument as units/second; `ForceInit()` resolves the path length.
Quaternion shortcuts use shortest-arc rotations.

`SetLink(game_object)` cleans up paused and active tweens when their owner is
destroyed. Link a root sequence. `LinkBehaviour` selects pooling policies.
`WaitFor...` returns an engine coroutine instruction; `AsyncWaitFor...` uses
the caller's existing asyncio loop.

Animate values with `DOTween.To(getter, setter, end_value, duration)`. Compose
tweens with `DOTween.Sequence().Append(tween).Join(other_tween)`. Configure before
playback or insertion into a sequence; each child belongs to one sequence.

`SetEase`, `SetDelay`, `SetLoops`, `SetUpdate` and `SetAutoKill` return the tween.
Control it with `Play`, `Pause`, `Restart`, `Rewind`, `Goto`, `Complete` and `Kill`.
Callbacks run on the engine thread. Times are seconds.

`From(value, set_immediately=False, relative=True)` fixes explicit endpoints when
called and delays writing them. Without a value, `From(set_immediately=False)`
captures the target at playback startup. See the repository README for string
and quaternion relative rules.
`ChangeStartValue`, `ChangeEndValue` and `ChangeValues` rewind regular value
tweeners, retaining consumed delay and playback state. A new positive duration
replaces the duration, or speed in speed-based mode. `ChangeEndValue(value, True)`
captures the current target as the new start and keeps the duration. These methods
have no effect on Sequence children; backwards playback stops at the beginning.

`Goto(seconds)` addresses the animation timeline without its initial delay.
On a sequence, `SetDelay(seconds)` prepends a repeating interval; pass
`as_prepended_interval_if_sequence=False` for a one-time startup delay. A sequence
callback can pause at its own position and `Play()` resumes there, including
joined and nested children. A root can change its update clock with `SetUpdate`
during playback; children use their root's clock.

Use `ShortcutExtensions.DOLocalMove(transform, (80, 20, 0), 0.4)` and the other
native target shortcuts for movement, scale, rotation, UI color/opacity/size,
slider values, materials, cameras, lights and audio. Python passes the target
explicitly rather than adding methods to native types. Kinematic Rigidbody
movement uses `move_position` in the Fixed phase.

Shortcuts set their target automatically. Control a group with `DOTween.Pause(target)`,
`Restart(target)` or `Kill(target)`, or assign `SetId("menu")` and filter by ID.
Sequences support whole-timeline easing, relative child values and restart/yoyo
loops. Incremental loops apply to value tweeners.

For interactive spring motion, construct `Spring(1, stiffness=200, damping=10)`,
call `Pull(0.2)` on interaction and `Update(fixed_delta)` on each simulation step.
Pulls preserve velocity; `Animate(target)` changes the anchor. Retire a spring
when `IsResting()` returns true. Springs are stateful, separately from seekable timelines.

Add **Animation / Tween Animation**, **Tween Path** or **Tween Visual Manager**
to configure native targets without a script. An empty Target means this object.
Paths use the native waypoint list and Scene position handles. Open **Animation /
Tween** for reversible preview; Save, Undo, selection changes and Play also restore
the authored values. Preview sends no gameplay events. Visual Manager supplies
explicit activation/deactivation actions for pooling.

Custom easing accepts a native `AnimationCurve` or a compiled CPU `EaseCurve`.
Jump, Punch, Shake and Spiral are seekable. Blendable movement, scale, rotation
and color preserve other writers. Authored runtime animations link to target
lifetime, including while paused.

String animation uses native graphemes, so a combining accent or joined emoji is
one step. `ShortcutExtensions.DOText(label, "Welcome 世界", 0.8)` reveals the text;
native color/size/br tags remain balanced. `DOCounter`, `DOFontSize` and
`DOMaxVisibleCharacters` animate counters, size and reveal limits.

For an existing label, animate its character geometry in one batch:

```python
from infernux_tween import DOTween, DOTweenTextAnimator

characters = DOTweenTextAnimator(label)
sequence = DOTween.Sequence()
sequence.Join(characters.Range().DOOffset((0, 12), 0.4).From())
sequence.Join(characters.Range().DOFade(0, 0.4).From())
sequence.SetLink(label.game_object)
```

`Character`, `Range`, `Word` and `Line` select native graphemes. Offsets use local
text coordinates, positive Y down; rotations use degrees. This animator owns the
Manual layer, so Text Animator effects and appearances can run alongside it.
Use one Manual-layer controller per label. `Reset` or `Dispose` restores that
layer; changing the layout retires old index tweens. Create character animations
after a `DOText` operation finishes changing the label's text.
