# Infernux Tween

Tween values, native scene objects and UI, compose timelines, and author animations in the Infernux editor. Python owns gameplay control and callbacks; the engine provides numerical kernels and AnimationCurve assets.

## Installation

Requires **Infernux 0.4.8 or newer**. Open the engine plugin manager, select **Infernux Tween** and install it. Numerical tools and curve assets are provided by the engine; the plugin installs its Python runtime and editor tools without building a native extension.

For development, use the current engine checkout or install its Python package, then run `python -m pip install -r sdk-requirements.txt`. `python package.py` exports the `.inxpkg` and release metadata used by the existing plugin publication flow.

## Script API

```python
import infernux_tween as tween
from infernux import AnimationCurve, Vector3

curve = AnimationCurve.ease_in_out(0, 0, 1, 1)
move = tween.twn_move(transform, Vector3(2, 1, 0), 1.0).set_ease(curve)
scale = tween.twn_scale(transform, 1.5, 1.0)

timeline = tween.sequence().append(move).join(scale)
timeline.set_loops(2, tween.LoopType.YOYO)
timeline.on_complete(on_finished)
```

Names use `twn_` shortcuts, snake_case methods, PascalCase classes and UPPER_SNAKE_CASE enum members. `from_` avoids the Python keyword. Configure a child before inserting it into a sequence.

`set_ease` accepts an `Ease`, an engine `AnimationCurve`, `EaseCurve`, or a four-argument function `(time, duration, overshoot_or_amplitude, period)`. A curve ease retains its original asset, so edits affect later samples.

Ordinary Python `int` and `float` endpoints remain supported. NumPy scalar endpoints select explicit numerical storage. Scalar, vector, color, quaternion, rectangle, string and array tweeners expose typed options and their interpolation plugin. Custom interpolation derives from `AbsTweenPlugin`.

## Available features

- Transform, Rigidbody, material, camera, light, sprite, line/trail and UI shortcuts.
- Linear, Catmull-Rom and Bezier paths, waypoint callbacks and orientation.
- Jump, Punch, Shake, Spiral, blendable motion and quaternion/Euler rotation.
- Append, prepend, join and insert; nested sequences, intervals and callbacks.
- Restart, yoyo and incremental loops; relative and From operations.
- Pause, resume, seek, restart, rewind, completion, target/ID controls and recycling.
- Normal, Late, Fixed and manual updates, including independent time.
- UI anchors, pivots, size, fill, color, text and character animation.
- Native line/trail updates and live engine curve assets.
- Coroutine waits, reusable yield instructions, async waits and scripted editor previews.
- Editable `TweenSettings` data assets, shared defaults and selectable rewind notifications.
- Native numerical snapshots and buffer jobs; large pure numerical batches release the GIL. Python callbacks execute with the interpreter state they require.

`play()` and `pause()` return the handle. Commands such as `force_init()`, `goto()`, `complete()`, `kill()` and `restart()` return None:

```python
move.set_auto_kill(False).pause()
move.force_init()
move.goto(.5)
```

## Editor

Add `Tween Animation`, `Tween Path` or `Tween Visual Manager` to a scene object. The plugin provides serialized settings, persistent events, path handles and editor preview. Preview Stop and leaving Edit mode restore authored values.

See the installed plugin pages for scene/UI examples and the complete scripting conventions.

## Build and checks

```powershell
python examples/quick_start.py
python -m pytest tests/test_package.py tests/test_curves.py tests/test_playback.py tests/test_paths.py tests/test_shortcuts.py
python package.py
```

`examples/quick_start.py --package out/infernux.tween.inxpkg` runs the installed archive in a small local project. Repository tools, examples, tests, CMake files and build outputs remain outside the plugin archive.

CI uses the current published SDK by default. Set `INFERNUX_SDK_PACKAGE` as a repository variable, or the manual workflow's `sdk_package` input, to build against a specific SDK wheel URL from the current engine build.

First-stage acceptance covers gameplay, authoring and long-running loops on Windows. Playback stores a bounded native phase and an integer loop counter per instance; shared timing recipes remain immutable. Further creation/batch optimizations should follow profiling in actual games.
