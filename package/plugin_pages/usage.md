# Tween

Animate values with `DOTween.To(getter, setter, end_value, duration)`. Compose
tweens with `DOTween.Sequence().Append(tween).Join(other_tween)`. Configure before
playback or insertion into a sequence; each child belongs to one sequence.

`SetEase`, `SetDelay`, `SetLoops`, `SetUpdate` and `SetAutoKill` return the tween.
Control it with `Play`, `Pause`, `Restart`, `Rewind`, `Goto`, `Complete` and `Kill`.
Callbacks run on the engine thread. Times are seconds.

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

This development build contains the playback core; visual components and paths
are not yet part of a public release.
