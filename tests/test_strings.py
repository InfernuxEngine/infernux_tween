import pytest

from infernux_tween import DOTween, Ease, LoopType, ScrambleMode, ShortcutExtensions as S, TweenManager


def test_unicode_replacement_from_speed_and_empty_destination():
    manager, value = TweenManager(), ["ABCDE"]
    tween = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "XY", 1)
    tween.SetEase(Ease.Linear).SetAutoKill(False).Goto(0.5)
    assert value[0] == "XBCD"
    tween.Goto(1)
    assert value[0] == "XY"
    tween.Rewind()
    assert value[0] == "ABCDE"
    value[0] = ""
    clusters = "e\u0301👨‍👩‍👧🇨🇳中"
    reveal = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), clusters, 2).SetSpeedBased().SetEase(Ease.Linear)
    reveal.ForceInit()
    assert reveal.Duration() == 2
    reveal.Goto(0.5)
    assert value[0] == "e\u0301"
    value[0] = "Ready"
    backwards = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "加载", 1).From().SetAutoKill(False)
    assert value[0] == "加载"
    backwards.Complete()
    assert value[0] == "Ready"
    clear = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "", 1).SetEase(Ease.Linear)
    clear.Goto(0.5)
    assert value[0] == "Re"
    clear.Goto(1)
    assert value[0] == ""


def test_native_markup_boundaries_and_a_grapheme_across_tags():
    manager, value = TweenManager(), [""]
    source = 'e<color="#ff0000">\u0301中<size=200%>文</size></color><br>Z'
    tween = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), source, 5).SetEase(Ease.Linear)
    tween.Goto(1)
    assert value[0] == 'e<color="#ff0000">\u0301</color>'
    tween.Goto(3)
    assert value[0] == 'e<color="#ff0000">\u0301中<size=200%>文</size></color>'
    tween.Goto(5)
    assert value[0] == source
    literal = manager.To(lambda: "", lambda text: value.__setitem__(0, text), "<color=no>text</color>", 1).SetEase(Ease.Linear)
    literal.Goto(0.25)
    assert value[0] == "<color"


def test_relative_incremental_sequence_and_repeatable_scramble_seek():
    manager, value = TweenManager(), ["A"]
    tween = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "中B", 1)
    tween.SetRelative().SetLoops(3, LoopType.Incremental).SetEase(Ease.Linear).SetAutoKill(False)
    sequence = manager.Sequence().Append(tween).SetAutoKill(False)
    sequence.Goto(2.5)
    assert value[0] == "A中B中B中"
    sequence.Rewind()
    assert value[0] == "A"
    value[0] = ""
    scrambled = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "<color=#ff0000>中文测试</color>", 2)
    scrambled.SetOptions(True, ScrambleMode.Custom, "甲乙丙丁戊", seed=17).SetEase(Ease.Linear)
    scrambled.Goto(0.5)
    sampled = value[0]
    assert sampled.startswith("<color=#ff0000>中</color>")
    scrambled.Goto(1.3).Goto(0.5)
    assert value[0] == sampled
    scrambled.Goto(2)
    assert value[0] == "<color=#ff0000>中文测试</color>"
    with pytest.raises(ValueError, match="alphabet"):
        manager.To(lambda: "", lambda text: None, "x", 1).SetOptions(True, ScrambleMode.Custom)


def test_explicit_string_from_preserves_its_type_specific_relative_order_and_changed_endpoints():
    manager, value = TweenManager(), ["C"]
    tween = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "E", 2)
    tween.From("F", set_immediately=False, relative=True).SetSpeedBased().SetAutoKill(False)
    assert value[0] == "C"
    tween.Goto(0)
    assert value[0] == "FC" and tween.Duration() == 0.5
    tween.ChangeValues("新起点", "中文目标", 2).Complete()
    assert value[0] == "中文目标" and tween.Duration() == 2
    value[0] = "C"
    boolean = manager.To(lambda: value[0], lambda text: value.__setitem__(0, text), "E", 1).From(True)
    assert value[0] == "E"
    boolean.Complete()
    assert value[0] == "C"


def test_native_ui_text_shortcuts_use_integer_counts_and_explicit_rich_text(monkeypatch):
    from types import SimpleNamespace
    from infernux.ui import UIText
    target = UIText()
    target.text = ""
    try:
        S.DOText(target, "<color=#ff0000>中文</color>", 1).SetEase(Ease.Linear)
        DOTween.Update(0.5)
        assert target.rich_text and target.text == "<color=#ff0000>中</color>"
        DOTween.Clear()
        S.DOCounter(target, 1000, 5000, 1).SetEase(Ease.Linear)
        DOTween.Update(0.5)
        assert target.text == "3,000"
        DOTween.Clear()
        geometry = SimpleNamespace(visible_characters=-1)
        target._text_geometry = geometry
        monkeypatch.setattr(target, "_resolve_text_geometry", lambda: geometry)
        S.DOMaxVisibleCharacters(target, 10, 1).SetEase(Ease.Linear)
        DOTween.Update(0.5)
        assert target.max_visible_characters == 5 and type(target.max_visible_characters) is int
    finally:
        DOTween.Clear()
