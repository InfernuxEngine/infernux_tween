# Infernux Tween

Official animation plugin for Infernux, maintained independently of the engine.
Requires Infernux **>=0.4.3**. Native integration uses the **0.4.3 build 2** SDK;
project-script imports additionally need the preload-library import fix currently
under verification in the engine. No public plugin release is available yet.

**In development.** No public plugin version is advertised yet. The current core
implements value tweens, easing, playback controls, restart/yoyo/incremental value
loops, separate update clocks, nested sequences and native target shortcuts.
Authoring components, paths and the remaining product/platform checks are still
being built. Incremental loops apply to value tweeners; sequences support restart
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
kinematic `move_position` in Fixed updates. Quaternion rotation, paths and the
remaining target-specific methods are not implemented yet.

Use CPython 3.13. For development, install `sdk-requirements.txt`, run
`python -m pytest` and `python package.py`. The output is a normal `.inxpkg`;
users will install it through the official plugin catalog without pip or Git.
See [maintenance](MAINTAINING.md) for the independent release workflow.

The API names and common behaviors are informed by the public
[DOTween documentation](https://dotween.demigiant.com/documentation.php).
Implementation is original Python code; no DOTween/Unity binaries are bundled.
