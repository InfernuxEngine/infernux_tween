# Infernux Tween

Official animation plugin for Infernux, maintained independently of the engine.
Requires Infernux **>=0.4.3**; development and integration use the **0.4.3 build 2** hotfix.

**In development.** No public plugin version is advertised yet. The current core
implements value tweens, easing, playback controls, restart/yoyo/incremental value
loops, separate update clocks and nested sequences. Target shortcuts, authoring
components, paths and the remaining product/platform checks are still being built.

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

Use CPython 3.13. For development, install `sdk-requirements.txt`, run
`python -m pytest` and `python package.py`. The output is a normal `.inxpkg`;
users will install it through the official plugin catalog without pip or Git.
See [maintenance](MAINTAINING.md) for the independent release workflow.

The API names and common behaviors are informed by the public
[DOTween documentation](https://dotween.demigiant.com/documentation.php).
Implementation is original Python code; no DOTween/Unity binaries are bundled.
