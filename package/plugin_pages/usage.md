# Tween

Animate values with `DOTween.To(getter, setter, end_value, duration)`. Compose
tweens with `DOTween.Sequence().Append(tween).Join(other_tween)`. Configure before
playback or insertion into a sequence; each child belongs to one sequence.

`SetEase`, `SetDelay`, `SetLoops`, `SetUpdate` and `SetAutoKill` return the tween.
Control it with `Play`, `Pause`, `Restart`, `Rewind`, `Goto`, `Complete` and `Kill`.
Callbacks run on the engine thread. Times are seconds.

This development build contains the playback core; visual components and paths
are not yet part of a public release.
