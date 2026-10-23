# Infernux Tween

Official animation plugin for Infernux, maintained independently of the engine.
Requires Infernux **0.4.3 build 3 or later**, including the preload-library import
and reload fixes. No public plugin release is available yet.

**In development.** No public plugin version is advertised yet. The current core
implements value tweens, easing, playback controls, restart/yoyo/incremental value
loops, separate update clocks, nested sequences and native target shortcuts.
Authoring components are implemented and undergoing Editor integration checks;
the remaining product/platform checks are in progress. Incremental loops apply to
value tweeners; sequences support restart
and yoyo loops, whole-sequence easing and relative child values.

```python
from infernux_tween import DOTween, Ease, LoopType

fade = DOTween.To(lambda: group.alpha,
                 lambda alpha: setattr(group, "alpha", alpha),
                 0.0, 0.4).SetEase(Ease.InOutSine)

sequence = DOTween.Sequence().Append(fade).AppendInterval(0.2)
sequence.AppendCallback(on_finished).SetLoops(2, LoopType.Yoyo)
```

The installed plugin owns its engine callbacks. Empty or fully paused animation
groups do not register a per-frame callback. Manual tweens advance only through
`DOTween.ManualUpdate(scaled_delta, unscaled_delta)`.
Editor Stop clears owned tweens, so restarting Play cannot retain old scene targets;
pausing and resuming Play preserve animation state.

Python uses explicit targets instead of adding extension methods to engine types:

```python
from infernux_tween import DOTween, ShortcutExtensions as Tween

Tween.DOLocalMove(transform, (80, 20, 0), 0.4)
Tween.DOScale(transform, 1.2, 0.2)
Tween.DOFade(group, 0, 0.3)
DOTween.Pause(transform)
DOTween.Restart(transform)
```

Shortcuts cover position/scale axes, Euler rotation (Fast/FastBeyond360), UI color,
opacity and size, slider/progress values, material color/float, camera properties,
light color/intensity and audio volume/pitch. Rigidbody movement uses the engine's
kinematic `move_position` in Fixed updates. Quaternion rotation uses shortest-arc
spherical interpolation; Euler rotation supports explicit full turns.

| API convention | Python mapping |
| --- | --- |
| Target extension methods | Pass the native target first: `Tween.DOMove(transform, position, seconds)`. |
| Typed `To` overloads | Use `DOTween.To(getter, setter, end_value, seconds)`; the end value selects scalar, vector, color or string interpolation. |
| Enum member named `None` | Use `AxisConstraint.None_` or `ScrambleMode.None_`; `None` is a Python keyword. |
| Material float property | Use `Tween.DOFloat(material, end_value, property_name, seconds)`. |
| UI transform shortcuts | Use native position, `DOSize` and UIGroup opacity; there is no separate RectTransform wrapper. |

Add **Animation / Tween Animation**, **Tween Path** or **Tween Visual Manager**
to author animation in Inspector. Empty Target means the owning object; material
targets use the standard material asset field. Animation components expose
`GetTween`, `GetTweens`, `DOPlay`, `DOPause`, `DORestart`, `DORewind`, `DOComplete`
and `DOKill`. They create no runtime tween in Edit mode. Visual Manager applies
explicit enable/disable actions for pooled objects.

Automatic target selection resolves once when creating a tween. Physics motion
uses an attached Rigidbody; a single compatible visual component is selected
directly. Multiple candidates require an explicit choice. Materials always use
the explicit asset field. The Tween panel displays active/playing root counts
by update clock; `DOTween.GetDiagnostics()` exposes the same snapshot to tools.

The **Animation / Tween** panel previews selected authored components without
gameplay events. Stop, Save, Undo, selection changes and Play restore captured
values. Path waypoints use the native serialized list and Scene position handles;
dragging commits through the editor's component transaction service.

Paths support Linear, Catmull-Rom and Cubic Bezier curves, closure, relative
coordinates, arc-length speed, axis locks, look-at orientation and waypoint
callbacks. `SetSpeedBased()` interprets the duration argument as units/second;
use `SetEase(Ease.Linear)` for constant speed and `ForceInit()` before querying
the computed duration or path length. Speed-based tweeners remain root timelines.
`SetOptions(AxisConstraint.Y, snapping=True)` keeps other axes live. Integer
values are rounded; `alpha_only=True` is explicit for RGBA lists.

`SetEase(engine_curve)` accepts the engine's authored `AnimationCurve`. The
component's Custom Curve toggle opens the existing curve editor. For longer CPU
key lists, use `EaseCurve(keys, pre_wrap="repeat", post_wrap="ping_pong")`; keys
carry time, value and incoming/outgoing tangents. The sampler compiles Hermite
segments once and supports arbitrary ordered key counts.

Jump supports multiple arcs and relative destinations. Punch and seeded Shake
restore the starting pose on completion and can be sampled with `Goto` without
accumulating offsets. Spiral supports an authored axis, expansion/contraction and
axial depth. Blendable Move/Scale/Rotation/Color applies only its incremental share,
preserving simultaneous tweens and external changes. These motion shortcuts are
on `ShortcutExtensions`; their algorithms are independent implementations.

`SetLink(game_object, LinkBehaviour.PauseOnDisablePlayOnEnable)` binds animation
to object lifetime. A shared lifecycle component handles destruction even when
all tweens are paused, without an idle frame callback. Link a sequence's root.
Authored components link their runtime tween to the target automatically; destroying
an external target retires its tween even while paused.
`WaitForCompletion`, `WaitForKill`, `WaitForStart`, `WaitForRewind`,
`WaitForElapsedLoops` and `WaitForPosition` return engine coroutine instructions.
Their `AsyncWaitFor...` equivalents use the caller's running asyncio loop;
the plugin creates no event loop and does not poll it every frame.

`Spring(value, stiffness, damping)` supplies fixed-step damped motion for
interactive impulses. `Pull(amount)` preserves velocity; `Animate(target)` moves
the anchor. Call `Update(fixed_delta)` and use `IsResting()` to retire settled
effects. This integrator is separate from seekable Tween/Sequence timelines.

Use CPython 3.13. For development, install `sdk-requirements.txt`, run
`python -m pytest` and `python package.py`. The output is a normal `.inxpkg`;
users will install it through the official plugin catalog without pip or Git.
See [maintenance](MAINTAINING.md) for the independent release workflow.

String tweening uses native extended graphemes, including combining marks and
joined emoji. `DOText` enables/disables `UIText.rich_text` explicitly; native
color/size/br tags stay balanced while a prefix or suffix is shown. String `From`,
relative append, restart/yoyo, seeded scrambling and speed in characters/second
are supported. Incremental string loops append relative text. `DOCounter`,
`DOFontSize` and `DOMaxVisibleCharacters` cover common label animation.

`DOTweenTextAnimator(text)` animates native character geometry without requiring
Text Animator. Use `DOOffsetChar`, `DORotateChar`, `DOScaleChar`, `DOColorChar` or
`DOFadeChar`, or select `Range`, `Word` or `Line` for batched operations:

```python
from infernux_tween import DOTween, DOTweenTextAnimator

characters = DOTweenTextAnimator(label)
sequence = DOTween.Sequence()
sequence.Join(characters.Word(0).DOOffset((0, 20), 0.5).From())
sequence.Join(characters.Range().DOFade(0, 0.5).From())
```

Character offsets/scales use canvas X/Y and rotation uses degrees. The animator
owns the Manual geometry layer, leaving persistent effects and appearance layers
available to Text Animator. Each manager update uploads once per text, regardless
of the number of character tweens. A layout change refreshes geometry and kills
old index tweens. `Reset`/`Dispose` clear only owned deformations and tweens. Link
the root sequence to its GameObject for lifetime control.

A setter or callback exception terminates its owning root timeline and propagates
to the engine's normal error reporting. Failed actions are not replayed next frame.

The build 3 SDK is being validated against the engine source before the public
SDK pin changes. The current public build 2 SDK does not provide the string API.

The API names and common behaviors are informed by the public
[DOTween documentation](https://dotween.demigiant.com/documentation.php).
Implementation is original Python code; no DOTween/Unity binaries are bundled.
