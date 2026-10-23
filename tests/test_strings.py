import pytest

from infernux_tween import Ease, LoopType, ScrambleMode, shortcuts as S, TweenManager
import infernux_tween as tween


def test_unicode_replacement_from_speed_and_empty_destination():
    manager, value = TweenManager(), ["ABCDE"]
    tween = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "XY", 1)
    tween.set_ease(Ease.LINEAR).set_auto_kill(False).goto(0.5)
    assert value[0] == "XBCD"
    tween.goto(1)
    assert value[0] == "XY"
    tween.rewind()
    assert value[0] == "ABCDE"
    value[0] = ""
    clusters = "e\u0301👨‍👩‍👧🇨🇳中"
    reveal = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), clusters, 2).set_speed_based().set_ease(Ease.LINEAR)
    reveal.force_init()
    assert reveal.duration() == 2
    reveal.goto(0.5)
    assert value[0] == "e\u0301"
    value[0] = "Ready"
    backwards = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "加载", 1).from_().set_auto_kill(False)
    assert value[0] == "加载"
    backwards.complete()
    assert value[0] == "Ready"
    clear = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "", 1).set_ease(Ease.LINEAR)
    clear.goto(0.5)
    assert value[0] == "Re"
    clear.goto(1)
    assert value[0] == ""


def test_native_markup_boundaries_and_a_grapheme_across_tags():
    manager, value = TweenManager(), [""]
    source = 'e<color="#ff0000">\u0301中<size=200%>文</size></color><br>Z'
    tween = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), source, 5).set_ease(Ease.LINEAR)
    tween.goto(1)
    assert value[0] == 'e<color="#ff0000">\u0301</color>'
    tween.goto(3)
    assert value[0] == 'e<color="#ff0000">\u0301中<size=200%>文</size></color>'
    tween.goto(5)
    assert value[0] == source
    literal = manager.to(lambda: "", lambda text: value.__setitem__(0, text), "<color=no>text</color>", 1).set_ease(Ease.LINEAR)
    literal.goto(0.25)
    assert value[0] == "<color"


def test_relative_incremental_sequence_and_repeatable_scramble_seek():
    manager, value = TweenManager(), ["A"]
    tween = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "中B", 1)
    tween.set_relative().set_loops(3, LoopType.INCREMENTAL).set_ease(Ease.LINEAR).set_auto_kill(False)
    sequence = manager.sequence().append(tween).set_auto_kill(False)
    sequence.goto(2.5)
    assert value[0] == "A中B中B中"
    sequence.rewind()
    assert value[0] == "A"
    value[0] = ""
    scrambled = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "<color=#ff0000>中文测试</color>", 2)
    scrambled.set_options(True, ScrambleMode.CUSTOM, "甲乙丙丁戊").set_ease(Ease.LINEAR)
    scrambled.goto(0.5)
    sampled = value[0]
    assert sampled.startswith("<color=#ff0000>中</color>")
    scrambled.goto(1.3).goto(0.5)
    assert value[0] == sampled
    scrambled.goto(2)
    assert value[0] == "<color=#ff0000>中文测试</color>"
    with pytest.raises(ValueError, match="alphabet"):
        manager.to(lambda: "", lambda text: None, "x", 1).set_options(True, ScrambleMode.CUSTOM)


def test_explicit_string_from_preserves_its_type_specific_relative_order_and_changed_endpoints():
    manager, value = TweenManager(), ["C"]
    tween = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "E", 2)
    tween.from_("F", set_immediately=False, is_relative=True).set_speed_based().set_auto_kill(False)
    assert value[0] == "C"
    tween.goto(0)
    assert value[0] == "FC" and tween.duration() == 0.5
    tween.change_values("新起点", "中文目标", 2).complete()
    assert value[0] == "中文目标" and tween.duration() == 2
    value[0] = "C"
    boolean = manager.to(lambda: value[0], lambda text: value.__setitem__(0, text), "E", 1).from_(True)
    assert value[0] == "E"
    boolean.complete()
    assert value[0] == "C"


def test_native_ui_text_shortcuts_use_integer_counts_and_explicit_rich_text(monkeypatch):
    from types import SimpleNamespace
    from infernux.ui import UIText
    target = UIText()
    target.text = ""
    try:
        S.do_text(target, "<color=#ff0000>中文</color>", 1).set_ease(Ease.LINEAR)
        tween.update(0.5)
        assert target.rich_text and target.text == "<color=#ff0000>中</color>"
        tween.clear()
        S.do_counter(target, 1000, 5000, 1).set_ease(Ease.LINEAR)
        tween.update(0.5)
        assert target.text == "3,000"
        tween.clear()
        geometry = SimpleNamespace(visible_characters=-1)
        target._text_geometry = geometry
        monkeypatch.setattr(target, "_resolve_text_geometry", lambda: geometry)
        S.do_max_visible_characters(target, 10, 1).set_ease(Ease.LINEAR)
        tween.update(0.5)
        assert target.max_visible_characters == 5 and type(target.max_visible_characters) is int
    finally:
        tween.clear()
