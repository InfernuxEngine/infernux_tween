# Infernux Tween

Official value, scene and text animation plugin for Infernux. The plugin is maintained in its own repository and installed from the official Animation catalog. Version 0.1.1 is a development candidate and requires Infernux **0.4.3 hotfix 4 or later**. Its native character features cannot run on the build 3 SDK.

```python
import infernux_tween as tween
from infernux import Vector3

move = tween.do_local_move(transform, Vector3(80, 20, 0), 0.4)
move.set_ease(tween.Ease.IN_OUT_SINE)
sequence = tween.sequence().append(move).append_interval(0.2)
sequence.append_callback(on_finished).set_loops(2, tween.LoopType.YOYO)
```

All functions and methods use `snake_case`; classes use `PascalCase` and enum members use `UPPER_SNAKE_CASE`. Native targets are explicit first arguments. The keyword exception is `from_`. There is one API, with no historical name aliases or replacement namespaces.

## Values and timelines

- `to(getter, setter, end_value, duration)` preserves scalar, Vector2/3/4, Color, quaternion and string values. `to(setter, start_value, end_value, duration)` creates a virtual value tween.
- `to_axis`, `to_alpha` and `to_array` retain their typed endpoint and option semantics. Color is the engine's RGBA list; Vector4 is `vec4f`.
- `set_ease` accepts an `Ease` enum, a native `AnimationCurve`, an `EaseCurve`, or a callable with `(time, duration, overshoot_or_amplitude, period)`. Back and Elastic parameters and the Flash family are evaluated.
- `set_options` is typed: scalar snapping, vector axis/snapping, color alpha-only, Euler shortest route, or string rich text/scrambling. Enum arguments are enum objects, not strings.
- `set_as(Tween | TweenParams)` copies common settings and callbacks, without copying the target or type-specific options.
- Nested sequences support append, prepend, join, insert, intervals, callbacks, easing, restart, yoyo and incremental cycles. Children belong to their sequence and use its clock.

```python
value = tween.to(read_value, write_value, 20.0, 1.0)
value.from_(5.0, set_immediately=False, is_relative=True)
value.change_end_value(30.0, new_duration=0.5, snap_start_value=True)
```

`from_(is_relative)` is the one-boolean overload. `from_(set_immediately, is_relative)` is the two-boolean overload. To defer capture without an explicit starting value, use `from_(set_immediately=False, is_relative=False)`. Explicit endpoints are captured when the call is made. `goto(seconds)` excludes startup delay.

Configure before playback or sequence insertion. `force_init()` initializes values without treating the tween as already playing. Callback controls such as pause, seek, kill or replacement stop the current dispatch at their documented boundary. Times are seconds.

## Controls and clocks

Instance controls include `play`, `pause`, `restart`, `rewind`, `goto`, `complete`, `kill`, backwards playback, flip, toggle, smooth rewind and queries. `restart(include_delay=True, change_delay_to=-1)` can replace startup delay. Filtered module controls require a target or ID; `play_all`, `pause_all`, `kill_all` and the other `*_all` functions explicitly address all roots. Native target helpers such as `do_pause(target)` use the same manager.

`set_update` accepts a bool, an `UpdateType`, or an `UpdateType` and a bool. The bool selects independent time. `manual_update(scaled_delta, unscaled_delta)` advances only manual roots. `get_time_scale()` and `set_time_scale(value)` control the default manager. A separate `TweenManager` owns its own clocks and factories.

The installed plugin owns frame registrations; empty and fully paused groups do not perform idle updates. Editor Stop clears owned animations. `set_link(game_object, LinkBehaviour...)` handles owner lifetime, including paused roots. Coroutine and async wait methods use the engine coroutine service or the caller's existing asyncio loop.

## Native targets

Shortcuts cover Transform position/scale axes and Euler/quaternion rotation; native UI colors, size and Slider values; SpriteRenderer and LineRenderer colors; material color/float/vector properties; camera projection properties; lights; and audio volume/pitch. Rigidbody movement uses `move_position`/`move_rotation` in Fixed updates. Paths provide local/world coordinates, Linear/Catmull-Rom/Bezier, orientation, waypoint events, seek and Scene gizmos.

Graphic fades animate `color.a`, Canvas Group fades animate `alpha`, and Audio Source fades animate `volume`. Material named-property overloads use `(target, end_value, property, duration)`. Missing material properties do not produce a fake tween. `do_size_delta` maps the native UI width/height and accepts Vector2; the engine has no separate RectTransform wrapper.

Jump, Punch, Shake, Spiral and blendable transforms/colors share the standard clock. `ShakeRandomnessMode` selects Full or Harmonic sampling. Camera shake has its own parameter defaults. Procedural samples are generated once and remain seekable; they do not accumulate frame noise.

Native limitations are explicit: the engine currently has no writable camera aspect/viewport API, standard material texture offset/tiling, text face/outline/glow shader channels, or whole-UI Transform scaling. These are not represented by inert fields or font-size substitutions. `do_scale` accepts Transform; text character scaling is available below.

## Editor authoring

Add **Tween Animation**, **Tween Path** or **Tween Visual Manager** from Animation. Targets use native references and fields. Paths use the native list and Scene position handles. Open **Animation / Tween** for reversible preview. Stop, Save, Undo, selection changes and entering Play restore authored values. Preview does not send gameplay events.

Persistent On Start, Play, Update, Step Complete, Complete, Rewind, Kill and Tween Created lists use the engine's list/reference/Undo widgets and bind the exact component instance. Only representable primitive, GameObject and component arguments are offered. Unsupported annotations are not converted into string arguments. Replacing scripts invalidates cached method lists through the runtime epoch.

## Character animation

```python
from infernux import Vector3
from infernux_tween import TextTweenAnimator

characters = TextTweenAnimator(label)
sequence = tween.sequence()
sequence.join(characters.do_offset_char(0, Vector3(0, 12, 4), 0.4).from_())
sequence.join(characters.range().do_fade(0, 0.4).from_())
sequence.set_link(label.game_object)
```

Character offsets, Euler angles and scales are real Vector3 values. Uniform scale accepts a float. Punch/Shake, per-corner XYZ shifts and character/span skew use the same native geometry and scheduler. Glyphs in one grapheme share a pivot. Public character operations ignore invisible or invalid characters; their tween factories return `None`.

`range`, `character`, `word` and `line` are additional batch selections. Indexes address native graphemes, not UTF-16 code units. Public vectors follow Transform axes: positive Y up; the buffer converts to layout's positive Y down. Manual geometry, Effects and Appearance compose in that order. Use one Manual-layer controller per label. `reset()`/`dispose()` restore that layer, and a changed layout retires old-index tweens. Character changes share one native upload per manager update.

## Validation

Run `python -m pytest` with the matching published SDK from `sdk-requirements.txt`. Package tests install the archive into a clean project and verify library import/unload. Release acceptance additionally uses real Windows/Linux Editors and Players, Android, and Web on Windows/Linux. The ongoing native hotfix and strict-API candidate require renewed acceptance; prior 0.1.1 development results do not certify this revision.
