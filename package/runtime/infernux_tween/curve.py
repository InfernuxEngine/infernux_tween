"""Compiled Hermite easing with no GPU ramp key limit."""
from bisect import bisect_right


class EaseCurve:
    def __init__(self, keys, pre_wrap="clamp", post_wrap="clamp"):
        keys = tuple(keys)
        if not keys or any(a.time >= b.time for a, b in zip(keys, keys[1:])):
            raise ValueError("Curve keys must be nonempty and strictly ordered")
        if pre_wrap not in ("clamp", "repeat", "ping_pong") or post_wrap not in ("clamp", "repeat", "ping_pong"):
            raise ValueError("Curve wrap must be clamp, repeat or ping_pong")
        self.times = tuple(key.time for key in keys)
        self.first, self.last = keys[0].value, keys[-1].value
        self.pre_wrap, self.post_wrap = pre_wrap, post_wrap
        self._segments = []
        for a, b in zip(keys, keys[1:]):
            span = b.time-a.time
            outgoing, incoming = a.out_tangent*span, b.in_tangent*span
            self._segments.append((span, 2*a.value-2*b.value+outgoing+incoming,
                                   -3*a.value+3*b.value-2*outgoing-incoming, outgoing, a.value))

    def __call__(self, time):
        start, end = self.times[0], self.times[-1]
        if start == end:
            return self.first
        if time < start or time > end:
            wrap = self.pre_wrap if time < start else self.post_wrap
            if wrap == "clamp":
                return self.first if time < start else self.last
            width = end-start
            phase = (time-start) % (width if wrap == "repeat" else width*2)
            time = start+(phase if wrap == "repeat" else width-abs(phase-width))
        index = min(len(self._segments)-1, max(0, bisect_right(self.times, time)-1))
        span, a, b, c, d = self._segments[index]
        t = (time-self.times[index])/span
        return ((a*t+b)*t+c)*t+d
