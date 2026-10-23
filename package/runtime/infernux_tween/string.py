"""Seekable string replacement with native graphemes and balanced UI markup."""
from enum import Enum
from math import floor, isfinite
import random
import re
import string

from infernux.lib import TextLayout

from .core import LoopType, Tweener, _UNSET


class ScrambleMode(Enum):
    NONE = "None"
    ALL = "All"
    UPPERCASE = "Uppercase"
    LOWERCASE = "Lowercase"
    NUMERALS = "Numerals"
    CUSTOM = "Custom"


_TAG = re.compile(r"<[^>]*>")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")
_SIZE = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)%?\Z")


def _opening(token, font_size):
    name, equals, value = token.partition("=")
    if not equals:
        return False
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1]
    if name == "color":
        return _COLOR.fullmatch(value) is not None
    if name == "size" and _SIZE.fullmatch(value):
        size = float(value.rstrip("%")) * (font_size/100 if value.endswith("%") else 1)
        return isfinite(size) and 0 < size <= 4096
    return False


class _Text:
    def __init__(self, source, rich_text, font_size):
        self.source = source
        characters, sources, stack = [], [], []
        def emit(start, end, newline=False):
            styles = tuple(stack)
            if newline:
                characters.append("\n")
                sources.append((start, end, styles))
            else:
                characters.extend(source[start:end])
                sources.extend((i, i+1, styles) for i in range(start, end))
        if rich_text:
            cursor = 0
            for match in _TAG.finditer(source):
                emit(cursor, match.start())
                token = match.group()[1:-1]
                if token in ("br", "br/"):
                    emit(match.start(), match.end(), True)
                elif token.startswith("/") and stack and token[1:] == stack[-1][0]:
                    stack.pop()
                elif _opening(token, font_size):
                    stack.append((token.partition("=")[0], match.group()))
                else:
                    emit(match.start(), match.end())
                cursor = match.end()
            emit(cursor, len(source))
        else:
            emit(0, len(source))
        self.graphemes = TextLayout.split_graphemes("".join(characters))
        self.ranges = []
        offset = 0
        for cluster in self.graphemes:
            first, last = sources[offset], sources[offset+len(cluster)-1]
            self.ranges.append((first[0], last[1], first[2], last[2]))
            offset += len(cluster)

    def __len__(self): return len(self.graphemes)

    def slice(self, start, count):
        if count <= 0:
            return ""
        if start == 0 and count == len(self):
            return self.source
        first, last = self.ranges[start], self.ranges[start+count-1]
        return ("".join(tag for _, tag in first[2]) + self.source[first[0]:last[1]]
                + "".join(f"</{name}>" for name, _ in reversed(last[3])))

    def scrambled(self, start, glyphs):
        result = []
        for index, glyph in enumerate(glyphs, start):
            styles = self.ranges[index][2]
            result.append("".join(tag for _, tag in styles)+glyph
                          +"".join(f"</{name}>" for name, _ in reversed(styles)))
        return "".join(result)


class StringTweener(Tweener):
    def __init__(self, getter, setter, end_value, duration):
        super().__init__(getter, setter, end_value, duration)
        self._rich_text = True
        self._scramble_mode = ScrambleMode.NONE
        self._scramble_chars = None
        self._seed = 0
        self._font_size = 18.0

    def set_options(self, rich_text_enabled: bool, scramble_mode: ScrambleMode=ScrambleMode.NONE, scramble_chars: str|None=None):
        if not self._configure():
            return self
        if type(rich_text_enabled) is not bool or not isinstance(scramble_mode, ScrambleMode):
            raise TypeError("string options require bool and ScrambleMode")
        if scramble_chars is not None and not isinstance(scramble_chars, str):
            raise TypeError("scramble_chars must be str or None")
        mode = scramble_mode
        if mode == ScrambleMode.CUSTOM and not scramble_chars:
            raise ValueError("Custom scrambling needs a character alphabet")
        self._rich_text, self._scramble_mode = bool(rich_text_enabled), mode
        self._scramble_chars = scramble_chars
        if self._start is not None:
            self._prepare(self._start, self._end)
        return self

    def _initialize(self):
        if self._start is not None:
            return
        start, end = self._getter(), self._end
        if not isinstance(start, str):
            raise TypeError("String tween getter must return str")
        if self._manual_start is not _UNSET:
            start = self._manual_start
        if self._from:
            if self._from_value is _UNSET:
                start, end = end, start
            else:
                start = self._from_value+start if self._relative else self._from_value
        self._set_values(start, end)
        if self.loop_type == LoopType.INCREMENTAL and not self._append:
            raise ValueError("Incremental string loops require set_relative()")

    def _set_values(self, start, end):
        self._append = self._relative and not self._from
        self._prepare(start, end)
        self._start, self._end = start, end

    def _distance(self):
        return len(self._last)

    def _prepare(self, start, end):
        first, last = (_Text(value, self._rich_text, self._font_size) for value in (start, end))
        if self._scramble_mode != ScrambleMode.NONE:
            alphabet = {ScrambleMode.ALL: string.ascii_letters+string.digits,
                        ScrambleMode.UPPERCASE: string.ascii_uppercase,
                        ScrambleMode.LOWERCASE: string.ascii_lowercase,
                        ScrambleMode.NUMERALS: string.digits,
                        ScrambleMode.CUSTOM: self._scramble_chars}[self._scramble_mode]
            glyphs = TextLayout.split_graphemes(alphabet)
            rng = random.Random(self._seed)
            self._scramble = tuple(rng.choice(glyphs) for _ in range(max(64, len(last)*4)))
        self._first, self._last = first, last

    def _apply(self, progress, cycle, previous, callbacks):
        self._initialize()
        length = len(self._last)
        factor = min(1.0, max(0.0, self._ease(progress)))
        revealed = min(length, max(0, round(length*factor)))
        prefix = self._start if self._append else ""
        if self._append:
            prefix += self._end*self._incremental_cycles(cycle)
        if factor >= 1:
            value = prefix+self._end
        elif self._scramble_mode != ScrambleMode.NONE:
            offset = floor(progress*self._duration*60) % (len(self._scramble)-length+1)
            value = prefix+self._last.slice(0, revealed)+self._last.scrambled(revealed, self._scramble[offset:offset+length-revealed])
        elif self._append:
            value = prefix+self._last.slice(0, revealed)
        elif not length:
            value = self._first.slice(0, round(len(self._first)*(1-factor)))
        else:
            old_length = len(self._first)
            remaining = old_length-(revealed if old_length <= length else int(old_length*revealed/length))
            suffix = self._first.slice(revealed, remaining) if remaining > 0 and revealed < min(old_length, length) else ""
            value = self._last.slice(0, revealed)+suffix
        self._setter(value)
