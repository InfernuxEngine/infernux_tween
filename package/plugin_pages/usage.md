# Tween

Requires Infernux **0.4.3 hotfix 4 or later**.

```python
import infernux_tween as tween
from infernux import Vector2, Vector3

move = tween.do_local_move(transform, Vector3(80, 20, 0), 0.4)
move.set_ease(tween.Ease.IN_OUT_SINE)
tween.sequence().append(move).append_interval(0.1).append_callback(on_finished)
tween.do_size_delta(image, Vector2(240, 80), 0.3)
```

Use snake_case functions, PascalCase classes and UPPER_SNAKE_CASE enum members. Pass native targets explicitly. Enum arguments remain enum objects, string endpoints remain strings, and Color is the engine RGBA list.

`to`, `to_axis`, `to_alpha` and `to_array` create typed value animations. `set_ease` accepts an Ease enum, AnimationCurve, EaseCurve or a four-argument callable `(time, duration, overshoot_or_amplitude, period)`. Options depend on value type. `set_as` copies shared settings from a Tween or TweenParams.

A single bool in `from_(is_relative)` controls relative values; two bools mean `from_(set_immediately, is_relative)`. Use `from_(set_immediately=False, is_relative=False)` to defer capture without an explicit value. `from_(value, set_immediately=False, is_relative=True)` captures explicit endpoints immediately but defers writing. `change_start_value`, `change_end_value` and `change_values` accept `new_duration`; `goto(seconds)` excludes startup delay.

Configure before playback or insertion into a sequence. Sequences support intervals, nested children, join/prepend/insert callbacks and incremental cycles. Callback pause/seek/kill is respected during dispatch. Instance controls operate on one animation; filtered module controls require target/ID, while `*_all` controls explicitly select all roots. `set_link` ties lifetime to a GameObject.

Native shortcuts cover Transform, Rigidbody, materials, UI, sprites/lines, camera, light and audio properties. Rigidbody motion uses Fixed updates. UI fades change graphic alpha, while Canvas Group changes alpha and Audio Source changes volume. Named material properties precede duration. Paths have real local/world orientation, waypoint controls and gizmos. Jump/Punch/Shake/Spiral and blendable animations reuse the same timeline. See the repository README for native capabilities that the engine does not currently expose.

Add Tween Animation, Tween Path or Tween Visual Manager to author without code. **Animation / Tween** previews reversibly through the existing Inspector/Scene services. Save, Undo, selection changes and Play restore authored values. Persistent event lists bind exact component instances; unsupported argument types are not offered as strings. Preview sends no gameplay callbacks.

```python
characters = tween.TextTweenAnimator(label)
characters.do_offset_char(0, Vector3(0, 12, 4), 0.4).from_()
characters.range().do_fade(0, 0.4).from_()
```

Characters use native grapheme indexes and real Vector3 positions/rotations/scales. Positive Y follows Transform up. Per-corner shifts retain XYZ; skew spans include the final index. These operations own the Manual layer and compose with Text Animator Effects/Appearance. A changed layout retires old-index tweens; one manager tick commits the shared buffer once. `reset` and `dispose` restore this layer.

The plugin owns its frame callbacks. Empty/paused groups have no active update registration. Manual roots advance through `manual_update(scaled_delta, unscaled_delta)`; independent clocks use unscaled time. `get_time_scale`/`set_time_scale` control the default manager. Spring is a separate stateful helper; call `pull`, `animate` and `update` with your simulation clock.
