# Tween

Requires Infernux 0.4.8 or newer. Select **Infernux Tween** in the engine plugin
manager and install it. Native curve and numerical tools come with the engine;
plugin installation does not compile an additional native library.

## Loop playback state

Ordinary tween and sequence playback keeps a bounded native phase, an integer
completed-loop count and a separate delay clock. Accumulated time is a query and
timeline projection, rather than a growing Single accumulator used for updates.
Seeking, rewinding, restarting and reentrant controls synchronize that state.
Immutable timing recipes can be shared; playback state belongs to each instance.

Use `position` and `completed_loops()` to observe long-running loop progress.
Accumulated-time queries retain their public Single result. A frame that exactly
finishes the startup delay does not advance playback; the next positive playback
step starts the animation and its initial playback callbacks.
Each tween captures its `time_scale` before getter initialization; changes made
by that getter affect the next frame rather than the captured step.

Initial `on_start` and `on_play` callbacks read the phase before this frame is
applied. Pausing or seeking inside them preserves the pending frame; killing the
tween cancels it. Changes to values and duration affect its application. The
`on_update` callback then observes the applied phase.

## Settings assets and rewind notifications

`TweenSettings` is an engine `DataAsset`, using the standard project asset editor,
references and Player cooking format. Load a referenced settings asset in startup
or preload code and call `apply()` before creating tweens. Scripted configuration
also works:

```python
from infernux_tween import Ease, RewindCallbackMode, TweenSettings

TweenSettings(
    default_ease_type=Ease.IN_OUT_SINE,
    default_auto_kill=False,
    rewind_callback_mode=RewindCallbackMode.FIRE_ALWAYS_WITH_REWIND,
).apply()
```

Creation defaults affect new tweens; manager controls such as time scale and
rewind policy affect the current manager. `settings.apply(manager)` configures
an independent manager. `safe_mode_options` holds logging and nested-failure
policies. Editor preferences select preview controls and playing/paused lists.

`FIRE_IF_POSITION_CHANGED` only notifies actual returns to the start.
`FIRE_ALWAYS_WITH_REWIND` also notifies repeated explicit rewind commands.
`FIRE_ALWAYS` additionally notifies repeat backwards-play and smooth-rewind
requests. An already-rewound smooth rewind preserves direction, and
`rewind(include_delay=False)` skips the remaining startup delay.

## Smoothed frame time

Set `use_smooth_delta_time` to use the engine's `Time.smooth_delta_time` for automatic
playback. `max_smooth_unscaled_time` caps the independent clock consumed per frame
by Normal/Late animations; its default is approximately 0.15 seconds. Late reuses
Normal's unscaled sample. Fixed converts through the physics time scale. Manual
updates continue using the caller's explicit clock inputs.

```python
import infernux_tween as tween

tween.use_smooth_delta_time = True
tween.max_smooth_unscaled_time = 0.05
```

The filter follows scaled game frames, independently of GPU timing and editor
render averages. Its value transitions gradually after time-scale changes; pause
animations explicitly when they must freeze immediately.

## Usage

UI rectangles expose `anchor_min/max`, `pivot`, `size_delta`,
`anchored_position`, `anchored_position3d` and `offset_min/max` through a shared
native `rect_transform`. Width/height are the resolved dimensions; `size_delta`
is the size outside the anchor span. With full stretch, `Vector2(-32, -24)`
subtracts 32 and 24 logical pixels from the parent dimensions.
`twn_anchor_pos`, its axis variants and `twn_size_delta` animate those native
parameters. Batch field transfers use the same owner. World UI converts logical
pixels at 100 pixels per scene unit; ordinary Transform positions retain scene units.

Requires Infernux 0.4.8 or newer. Install Infernux Tween from the engine plugin manager. The engine supplies the native curve, layout and numerical interfaces.

```python
import infernux_tween as tween
from infernux import Vector2, Vector3

move = tween.twn_local_move(transform, Vector3(80, 20, 0), 0.4)
move.set_ease(tween.Ease.IN_OUT_SINE)
tween.sequence().append(move).append_interval(0.1).append_callback(on_finished)
tween.twn_size_delta(image, Vector2(240, 80), 0.3)
```

Use snake_case functions, PascalCase classes and UPPER_SNAKE_CASE enum members. Pass native targets explicitly. Enum arguments remain enum objects, string endpoints remain strings, and Color is the engine RGBA list.

## Coroutine waits and scripted preview

Use `yield move.wait_for_completion()` in an engine component coroutine, or
`await move.async_wait_for_completion()` inside an async task. Start, kill,
rewind, elapsed-loop and position waits follow the same naming.

Pass `return_custom_yield_instruction=True` to obtain a reusable instruction,
or construct `WaitForCompletion(move)` directly. Its read-only `keep_waiting`
property reflects current playback, including pause, replay and destruction.
The engine coroutine scheduler accepts these objects directly.

```python
from infernux_tween import TweenEditorPreview

TweenEditorPreview.prepare_tween_for_preview(move)
TweenEditorPreview.start(on_preview_updated=refresh_panel)
# Later, from an editor button or tool:
TweenEditorPreview.stop(reset_tween_targets=True)
```

Preparation selects manual updates, clears gameplay callbacks and prevents
auto-kill by default. Its `clear_callbacks`, `prevent_auto_kill` and `and_play`
arguments control those choices. `start` has no effect in Play mode; `stop`
unregisters the preview loop. `clear_tweens=False` keeps live prepared handles
for another preview. Plugin unload and entering Play stop scripted previews.

`to`, `to_axis`, `to_alpha` and `to_array` create typed value animations. `set_ease` accepts an Ease enum, AnimationCurve, EaseCurve or a four-argument callable `(time, duration, overshoot_or_amplitude, period)`. Options depend on value type. `set_as` copies shared settings from a Tween or TweenParams.

A single bool in `from_(is_relative)` controls relative values; two bools mean `from_(set_immediately, is_relative)`. Use `from_(set_immediately=False, is_relative=False)` to defer capture without an explicit value. `from_(value, set_immediately=False, is_relative=True)` captures explicit endpoints immediately but defers writing. `change_start_value`, `change_end_value` and `change_values` accept `new_duration`; `goto(seconds)` excludes startup delay.

Configure before playback or insertion into a sequence. Sequences support intervals, nested children, join/prepend/insert callbacks and incremental cycles. Callback pause/seek/kill is respected during dispatch. Instance controls operate on one animation; filtered module controls require target/ID, while `*_all` controls explicitly select all roots. `set_link` ties lifetime to a GameObject.

Native shortcuts cover Transform, Rigidbody, materials, UI, sprites/lines, camera, light and audio properties. Rigidbody Move/Rotate/LookAt/Jump/Spiral inherit the manager's update phase; Rigidbody paths select Fixed. Choose `set_update(UpdateType.FIXED)` explicitly for other automatic physics-step playback. UI fades change graphic alpha, while Canvas Group changes alpha and Audio Source changes volume. Named material properties precede duration. Paths have real local/world orientation, waypoint controls and gizmos. Jump/Punch/Shake/Spiral and blendable animations reuse the same timeline. See the repository README for native capabilities that the engine does not currently expose.

Add Tween Animation, Tween Path or Tween Visual Manager to author without code. **Animation / Tween** previews reversibly through the existing Inspector/Scene services. Save, Undo, selection changes and Play restore authored values. Persistent event lists bind exact component instances; unsupported argument types are not offered as strings. Preview sends no gameplay callbacks.

Authoring `has_on_*` flags default to false and event objects to None. Enable an
event in the Inspector before adding entries. In scripts, assign a UIEvent, add
listeners and enable its flag before creating the tween. Changing the flag or
replacing the event later does not replace an already-bound delegate; recreate
the tween to use it. Disabled playback events are cleared at creation, while
Tween Created is only gated. Serialization preserves authored entries and event
presence, not runtime listeners. Older code must explicitly enable events.
Disposal clears `animation.tween` to None; re-enabling the GameObject does not
automatically recreate a tween after its initial lifecycle generation.

`target` persists the actual animated component. `target_go` and `target_is_self`
select the GameObject; `tween_target_is_target_go` selects the control group.
These are separate references. World Move uses the stored component; Local Move,
Local Rotate and Scale use the selected GameObject's Transform. Configure scripts
explicitly, for example:

```python
animation.animation_type = animation.AnimationType.MOVE
animation.target_is_self = False
animation.target_go = actor
animation.target = actor.transform
animation.target_type = animation.TargetType.TRANSFORM
animation.animation_valid = True
animation.end_value_v3 = (4, 0, 0)
animation.create_tween(and_play=True)
```

`animation_valid` is authoring readiness; the engine's `is_valid` still means a
live component handle. New components start unconfigured. Editor validation
records an unambiguous target. Endpoints use `end_value_float/v2/v3/color/string`,
`end_value_rect` (engine Rect) or `end_value_transform` (persisted Transform).
With `use_target_as_v3=True`, creation reads the endpoint's world position and
disables relative motion; a missing endpoint means zero.

`is_active` gates automatic generation, not manual CreateTween. Generation runs
in Awake, or Start for a Transform endpoint, and is not repeated on pool activation.
An invalid recipe preserves an existing tween even when regeneration is requested.
Color/Fade force absolute mode; Light Fade changes intensity. The six Camera
animation types include projection aspect, background, FOV, orthographic size
and pixel/normalized viewports, with From and relative modes. Special targets and
some UI capabilities still need implementation; enum presence is not full parity.

`TweenPath.path` exposes the current path. Baked authoring points are world-space;
a local path's runtime startup converts the public path to local coordinates.
`get_draw_points()` returns those path coordinates; `get_world_draw_points()`
explicitly converts them for Scene drawing. Curve drawing density is independent
of `path_resolution`, which controls distance estimation. Runtime conversion does
not overwrite the authored recipe. Combined rotation locks such as
`AxisConstraint.X | AxisConstraint.Y` persist through serialization. A missing
look target leaves orientation unchanged while the path continues to move.

```python
characters = tween.TextTweenAnimator(label)
characters.twn_offset_char(0, Vector3(0, 12, 4), 0.4).from_()
characters.range().twn_fade(0, 0.4).from_()
```

Characters use native grapheme indexes and real Vector3 positions/rotations/scales. Positive Y follows Transform up. Per-corner shifts retain XYZ; skew spans include the final index. These operations own the Manual layer and compose with Text Animator Effects/Appearance. A changed layout retires old-index tweens; one manager tick commits the shared buffer once. `reset` and `dispose` restore this layer.

The plugin owns its frame callbacks. Empty/paused groups have no active update registration. Manual roots advance through `manual_update(scaled_delta, unscaled_delta)`; independent clocks use unscaled time. `get_time_scale`/`set_time_scale` control the default manager. Spring is a separate stateful helper; call `pull`, `animate` and `update` with your simulation clock.

Custom interpolation plugins extend `AbsTweenPlugin[Value, Storage, Options]` and
use `to(plugin, getter, setter, end_value, duration)`. The returned `TweenerCore`
exposes `start_value`, `end_value`, `change_value`, `plug_options`, `getter` and
`setter`. Storage need not support generic arithmetic. For Python value objects,
set `storage_default` to a fresh-value factory; its default None is for reference storage.

Implement conversion, both `set_from` forms, relative endpoints, change values,
speed duration, evaluation and Reset callbacks. Keep per-tween state in its own
values/options rather than a shared plugin instance. Options need no-argument
construction and `reset()`. Replacing options copies fields; editing the tween's
option fields affects that tween. Destruction/recycling calls plugin and options
Reset; plugins own cleanup of their storage references.

Direct built-in `evaluate_and_apply` calls use the supplied elapsed time and
duration without advancing or retiming their owner. Value arguments and options
are captured before easing callbacks; edits affect subsequent calls. Segment
arrays retain shared storage, so edits to their elements during easing contribute
to the current interpolation. Array easing receives segment-local seconds and
the segment duration.

Plugins can use `EaseManager.evaluate(tween, elapsed, duration, amplitude, period)`,
the explicit Ease/callback overload or `to_ease_function`. Public
`ease_overshoot_or_amplitude` and `ease_period` are mutable. Reserved INTERNAL_*
eases represent internal states: pass a curve or callback for custom easing;
INTERNAL_CUSTOM without a callback fails.

`EaseManager.evaluate_unclamped(t, time, duration, overshoot_or_amplitude, period)`
also applies the reference incremental-loop offsets for custom plugins. Use
`start + change * factor` with its result when your interpolation should support
incremental loops. It includes the child and immediate parent, not every ancestor.

IDs use independent `id`, `string_id` and `int_id` channels. `set_id("menu")`
and `set_id(7)` select the typed channels; `set_id(object_id=value)` explicitly
selects the object overload. Larger-than-32-bit integers are object IDs.
Queries use the same dispatch, and bool/int/float objects remain distinct.
`set_as` copies every ID while retaining the destination target. Disposal clears
IDs and targets. `TweenParams.params.clear()` reuses a shared settings recipe.

Fluent registrations remain `on_play(...)`, `on_update(...)`, etc. Raw delegates
are `start_callback`, `play_callback`, `pause_callback`, `rewind_callback`,
`update_callback`, `step_complete_callback`, `complete_callback`, `kill_callback`
and `waypoint_change_callback`. Assign None to clear a delegate. The raw writable
direction flag is `backwards`; `is_backwards()` remains an active-state query.

Pause callbacks remain assigned after disposal and typed pool reuse.
Clear `pause_callback` explicitly before recycling
if its captured objects should be released. `debug_mode`, `use_safe_mode` and
`debug_store_target_id` must all be enabled to capture target labels, which clear
on disposal. Broader logging/reporting settings remain pending.

`twn_fill_amount(image, end_value, duration)` animates actual filled geometry.
Assign a texture and set `image.image_type=image.Type.FILLED`, then configure
`fill_method`, `fill_origin` and `fill_clockwise`. Horizontal, vertical and radial
90/180/360 are supported. Set the method before the origin: method changes reset
the origin. UV cropping preserves the source image, while rotation/mirroring use
the full rectangle's center. From/relative behavior also works through the
authoring component's `FILL_AMOUNT`, with reversible preview.

An untextured image retains its full rectangle, and default pointer hit regions
stay rectangular. This feature requires the matching updated engine SDK; a
plugin update alone cannot add the native drawing interface to an older runtime.

For a child of an auto-layout UIFrame, animate independent layout input rather
than rewriting the widget's authored dimensions:

```python
from infernux.ui import UILayoutElement
import infernux_tween as tween

layout = panel.game_object.add_component(UILayoutElement)
layout.min_width = layout.min_height = 0
layout.preferred_width, layout.preferred_height = 120, 60
layout.flexible_width = layout.flexible_height = 0
tween.twn_preferred_size(layout, (200, 60), 0.4).set_ease(tween.Ease.IN_OUT_SINE)
```

`twn_min_size` changes minimum dimensions; `twn_flexible_size` changes the two
expansion weights, not pixel sizes. All three target a UILayoutElement and support
snapping, From and relative playback. The parent computes the final rectangle
using available space and sibling input. Negative values are unset; a zero
flexible weight explicitly disables expansion. Multiple elements resolve each
property by highest priority, then highest value at the same priority.

Existing Fixed/Hug/Fill widgets without an element retain their layout behavior.
A neutral UIFrame can serve as a spacer. This requires the matching engine SDK;
full RectTransform support, including anchor and pivot shortcuts, remains pending.

Punch startup forces OutQuad and clears relative/speed-based settings, including
an Ease configured before startup. Motion uses segments rather than the former
sine approximation. High-level `twn_punch_*` returns None for nonpositive duration.

Transform `twn_jump` / `twn_local_jump` returns a Sequence using the manager's
default Ease. Use `.set_ease(tween.Ease.LINEAR)` for uniform horizontal travel.
The destination's height offset has its own easing. Actual-reference checks
cover seeking and manual playback; Rigidbody still needs separate physics-step
acceptance.

Shake consumes the engine's shared random stream. Seed once for a reproducible
session, or capture state before creating an effect:

```python
from infernux import Random
import infernux_tween as tween

Random.init_state(123)
checkpoint = Random.state
effect = tween.twn_shake_position(target, 0.4, strength=0.2)

# Restore only when regenerating the same random effect is intended.
Random.state = checkpoint
```

Seeking, rewinding and replaying an existing tween reuse its segments without
new draws. Separate tweens advance the shared stream. Scalar camera Shake is
planar, vector strength can add spatial motion, and camera rotation is captured
at startup. This requires the matching SDK with the native Random interface.

Spiral uses the shared custom-plugin execution path and its captured local
position (Transform) or world position (Rigidbody). Its `frequency` changes the
radius; `depth` controls travel along the oriented axis. A zero/tiny axis falls
back to forward, and a zero speed selects the shortcut default. Use a positive
frequency for finite motion. Relative mode does not add the origin to the axis,
and From does not implement reverse Spiral playback. The default ease and update
phase come from the manager; choose Linear or Fixed explicitly when required:

```python
effect = tween.twn_spiral(body, 2.0, Vector3(0, 0, 1),
                          tween.SpiralMode.EXPAND_THEN_CONTRACT,
                          speed=0.75, frequency=5.0, depth=2.0)
effect.set_ease(tween.Ease.LINEAR).set_update(tween.UpdateType.FIXED)
```

The public `SpiralPlugin.get()` and `SpiralOptions` also work with `to(plugin,
getter, setter, axis, duration)` on the normal `TweenerCore` lifecycle and pool.


## Runtime identity and rectangle coordinates

`version` is the installed plugin version. `instance` is None before default-manager
initialization and after `clear(destroy=True)`; otherwise it is that live manager.
Set `draw_gizmos = False` to skip runtime path debug geometry. Edit-mode waypoint
handles stay available.

`switch_to_rect_transform(source, target)` converts rectangle centres to a target
anchored position. It includes stretched dimensions, pivots, target-plane projection
and world UI units, and does not assign the positions. The source centre offset
uses unrotated screen coordinates; this is not arbitrary camera-to-camera projection.

```python
position = tween.switch_to_rect_transform(source_image, target_image)
tween.twn_anchor_pos(target_image, position, .4)
```


## Optional target interfaces and Editor reports

Scrolling owners can expose writable `normalized_position` (Vector2),
`horizontal_normalized_position` and `vertical_normalized_position` properties.
Use `twn_normalized_pos`, `twn_horizontal_normalized_pos` or
`twn_vertical_normalized_pos`; each accepts an optional `snapping=False`.
The owner retains responsibility for clipping, bounds, input and layout.
These shortcuts do not create a scrolling widget.

`twn_set_float(target, float_name, end_value, duration)` calls numeric
`get_float(name)` and `set_float(name, value)` methods. The target owns parameter
exposure, units, missing-parameter behavior and audio-thread publication. This
interface also works with Material values; it does not create a mixer asset.

Set `show_editor_report = True` to print peak root tweener/sequence counts and
handled errors when Editor Play stops. `get_editor_report()` reads the counters.
Counting occurs at ownership changes and adds no per-frame traversal.
## Single-precision values

Ordinary Python floating endpoints use double-precision playback. Use a NumPy
`float32` endpoint to select explicit single precision; the setter receives
`numpy.float32`, including relative values, From and loops.

```python
import numpy as np

value = [np.float32(0)]
handle = tween.to(lambda: value[0], lambda v: value.__setitem__(0, v), np.float32(1), .5)
handle.set_options(snapping=False)
```

Single- and double-precision numeric snapping run inside the prepared native
sampler. Value or option edits update the recipe; playback does not convert
output types in Python. Large single-precision buffer jobs write into existing
float32 buffers and release the GIL.

Explicit scalar endpoints also support NumPy `float64`, `int32`, `int64`,
`uint32` and `uint64`. Setters retain that type, and buffer jobs write the
corresponding dtype. Type and sampling entry points are bound at configuration.
`UintOptions.is_negative_change_value` stores the 32-bit unsigned direction.

Rectangle and string tweens expose the same core fields as scalar tweens.
Rectangles retain `Rect` values and the original getter/setter callbacks;
`RectOptions.snapping` controls native rounding for all four fields.
`StringOptions` exposes `rich_text_enabled`, `scramble_mode` and
`scrambled_chars`. Copied string options share their character array. Editing
that array updates the attached text plans once; playback does not scan it.
Direct `start_value` and `change_value` edits preserve the startup text-length
cache. Use `change_values` to rebuild the transition and its text lengths.

`to_array` exposes per-segment `start_value`, `end_value` and `change_value`
through native `Vector3Array` storage. Creation copies the requested endpoints.
After startup, changing an endpoint does not recalculate its change value;
`change_values` rebuilds the transition. Editing a start/change element or its
coordinates reaches the prepared native sampler directly. Bulk sampling takes
one stable copy before releasing the GIL, so concurrent edits affect subsequent
work. `Vector3ArrayOptions` retains the declared axis and snapping options.

Euler rotation tweens expose `QuaternionOptions`: `rotate_mode`,
`axis_constraint`, `up`, `dynamic_look_at`, and
`dynamic_look_at_world_position`. The getter/setter use quaternions while core
start/end/change fields use Euler `Vector3` values. Ordinary rotation and both
axis-add modes share native sampling. Dynamic look-at updates the native end
and change fields without rebuilding the sampler each frame. Bulk quaternion
sampling freezes its inputs and releases the GIL for large jobs.

Rotation shortcuts declare their types at creation. For generic `to` with a
Vector3 endpoint, an early plugin/options query uses the getter's return type
annotation; without one, it reads the getter once to resolve vector versus
quaternion storage. Startup still captures the current value. A getter declared
`def read_rotation() -> quatf:` provides this type information without that read.
Unsigned 64-bit arithmetic preserves integer bits using native decimal
calculation; overflow follows `use_safe_mode` and seek/update ownership rules.
No Python decimal computation or additional numerical library is required.

Ordinary `Vector2`, `Vector3`, and `vec4f` tweens read native start/change
storage directly. Edits such as `handle.start_value.x = 5` or
`handle.change_value.y = 40` affect subsequent samples without replacing the
prepared job. Supplied or reassigned vectors are copied by value; editing the
caller's original vector does not change the tween. Direct endpoint edits do
not recalculate the change: use `change_values` to redefine the transition.
Bulk sampling freezes the batch inputs before releasing the GIL, so concurrent
edits affect later calls. Ordinary Python `int` and `float` values and type
annotations remain supported without user-side NumPy scalar declarations.

Path tweens expose `PathOptions` and `PathPlugin.get()` with the shared
`TweenerCore` start/end/change fields, getter, setter, and options. Define a
pending path with `Path(PathType.CATMULL_ROM, waypoints, 10)` and pass it to the
explicit-plugin `to` overload. Startup builds the arc tables and native control
points. Editing control points retains the existing arc tables, and native
sampling reads their new coordinates directly. Use `Path.compile()` to capture
an independent snapshot with freshly computed arc tables for bulk computation.
The compiled snapshot remains stable and supports released-GIL sampling.

Direct start/end replacements do not redirect the path being sampled.
`change_end_value` finalizes the new endpoint path and updates the change path;
path queries read the endpoint path. `PathOptions` includes mode, orientation,
axis locks, closure, local space, targets, and startup state. Option copies copy
vector and quaternion values; replacing options detaches the previous options.

Finalized Bezier paths expose endpoints through `wps` and `ControlPoint(a, b)`
values through `control_points`; `points` retains the expanded editor recipe
view. These interfaces read the same native data, so coordinate edits affect
subsequent samples directly. Replacing either array preserves the arc tables
and the other array. Native array references can be shared, and old array views
remain valid. Bulk sampling freezes both endpoint and control arrays before
releasing the GIL.

`control_points = None` means the control array is absent; `control_points = []`
means an existing zero-length array. Nonlinear sampling reports an attribute
error or an index error respectively, without filling missing geometry.
Incremental loops build a translated copy from the current endpoints when the
loop index changes and reuse it within the same loop. Edits to the original
endpoint and control arrays are available when a new loop copy is built.
The `Path` owns this cache. Tweens sharing one path also share its loop cache
and lifetime; create separate paths when edits, looping or destruction should
be independent. Direct plugin evaluation uses the supplied `change_value` path's
cache, rather than borrowing a clone from the tween's original path.

`PathPlugin.get().set_orientation(options, tween, path, path_percentage, t_pos, update_notice)`
sets orientation independently, without advancing time, writing position or
dispatching tween callbacks. `path_percentage` is the normalized parameter after
arc-length remapping; `t_pos` is the current path position. Ordinary tweens and
sequences can supply a Transform, GameObject or Rigidbody target. The supplied
options remain unchanged. `PathPlugin.min_look_ahead` exposes the minimum look-ahead.

Pausing and resuming preserve creation order. Setter edits to later tweens are
visible during the current update, and installing, replacing or clearing an
update callback from its setter affects that dispatch. Sequences visit loop
boundaries and the current position separately; observable setter calls are
not merged. Child direction follows the current interval traversal and can
differ from the root sequence's playback direction.

`Path.wp_lengths` stores individual segment lengths, including its leading entry,
in a fixed-size `Float32Array`. It accepts ordinary numbers, supports item edits
and writable `memoryview` access, and can be replaced from a list. Edits affect
`goto_waypoint` and waypoint callbacks without rebuilding geometry or arc-length
sampling tables. Incremental clones share the array captured when they were
created; replacing the original array does not replace an existing clone's
reference. Destruction clears the field while existing array and buffer views
remain valid.

Custom waypoint lengths can produce a negative playback clock. Forward playback
retains that clock until it reaches zero and then continues normally. Reverse
playback returns to zero and pauses. Lifecycle and loop notifications remain
active during this recovery. Yoyo direction changes require an actual looping
timeline; selecting Yoyo for a single play does not reverse it.

Time seeking also dispatches waypoint callbacks. Pausing or seeking does not
cancel the current waypoint batch; Rewind can dispatch nested notifications.
Each notification reads the current callback, so replacements take effect in
the same batch. Clearing that callback, including through immediate disposal,
uses the configured exception policy for remaining calls. With safe mode
disabled, exceptions propagate without automatically destroying the failed handle.

Direct `PathPlugin.evaluate_and_apply` calls accept ordinary tweens and sequences.
They use the supplied time, duration, direction and completed-step count, and
store waypoint state on the actual caller without advancing its clock or
replacing its original plugin options. Prepared paths do not recapture a getter.
Option edits made by custom setters or ease functions affect later samples;
the current sample retains its incoming values. A target reference changed by
the setter is used by the current orientation calculation. An interval-only
sequence needs a lifecycle or update callback to start; a waypoint listener alone does
not provide timeline content.

Existing roots keep their creation order across pauses and phase changes. A
callback can resume an existing later root in the current update; new roots
start on the next update. Killing during dispatch marks a root inactive before
its deferred retirement. A future slot can retire at the end of the current
update; a slot already visited waits for the next visit to its phase. Kill
callbacks and pool reuse happen at retirement, in reverse visit order within
each batch. Global `clear()` unregisters all roots and clears pools directly;
it preserves fields on old handles and does not recursively dispose sequence
children or replay an already inactive root's deferred kill callback.
