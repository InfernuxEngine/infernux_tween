import pytest

from infernux.lib import SceneManager, Vector3
from infernux.ui import UIButton, UIGroup, UIImage, UISlider, UIText
from infernux_tween import DOTween, Ease, RotateMode, ShortcutExtensions as S


@pytest.fixture
def target():
    scenes = SceneManager.instance()
    scene = scenes.create_scene("Tween shortcut contract")
    obj = scene.create_game_object("Animated target")
    try:
        yield obj.transform
    finally:
        DOTween.Clear()
        scenes.unload_scene(scene)


def test_local_move_uniform_scale_and_filtered_target_control(target):
    target.local_position = Vector3(2, 4, 0)
    S.DOLocalMove(target, (6, 8, 0), 1).SetEase(Ease.Linear)
    S.DOScale(target, 2, 1).SetEase(Ease.Linear)
    DOTween.Update(0.5)
    assert (target.local_position.x, target.local_position.y) == pytest.approx((4, 6))
    assert target.local_scale.x == pytest.approx(1.5)
    assert DOTween.Pause(target) == 2
    DOTween.Update(1)
    assert target.local_position.x == 4
    DOTween.Restart(target)
    DOTween.Update(1)
    assert target.local_position.x == 6 and target.local_scale.z == 2


def test_independent_axes_keep_other_values_and_snap_only_the_selected_axis(target):
    target.position = Vector3(1, 2, 3)
    S.DOMoveX(target, 8, 1, snapping=True).SetEase(Ease.Linear)
    S.DOMoveY(target, 10, 1).SetEase(Ease.Linear)
    DOTween.Update(0.5)
    assert tuple(target.position) == pytest.approx((4, 6, 3))
    target.position = Vector3(target.position.x, target.position.y, 9)
    DOTween.Update(0.25)
    assert tuple(target.position) == pytest.approx((6, 8, 9))


def test_euler_rotation_uses_shortest_route_or_explicit_turns(target):
    target.local_euler_angles = Vector3(0, 0, 170)
    short = S.DOLocalRotate(target, (0, 0, -170), 1).SetEase(Ease.Linear)
    DOTween.Update(0.5)
    assert abs(target.local_euler_angles.z) == pytest.approx(180, abs=0.001)
    short.Kill()
    target.local_euler_angles = Vector3(0, 0, 0)
    S.DOLocalRotate(target, (0, 0, 540), 1, RotateMode.FastBeyond360).SetEase(Ease.Linear)
    DOTween.Update(0.25)
    assert target.local_euler_angles.z == pytest.approx(135, abs=0.001)
    DOTween.Update(0.25)
    assert target.local_euler_angles.z == pytest.approx(270, abs=0.001)


def test_ui_fade_color_size_and_slider_notification(target):
    group, text, image, button, slider = UIGroup(), UIText(), UIImage(), UIButton(), UISlider()
    text.color = [1, 0, 0, 1]
    image.color = [1, 1, 1, 1]
    image.width, image.height = 100, 20
    slider.minimum, slider.maximum = 0, 10
    values = []
    slider.on_value_changed.add_listener(values.append)
    S.DOFade(group, 0, 1).SetEase(Ease.Linear)
    S.DOFade(text, 0, 1).SetEase(Ease.Linear)
    S.DOColor(text, [0, 0, 1, 1], 1).SetEase(Ease.Linear)
    S.DOColor(button, [0, 0, 0, 1], 1).SetEase(Ease.Linear)
    S.DOSize(image, (200, 40), 1).SetEase(Ease.Linear)
    S.DOValue(slider, 8, 1, notify=False).SetEase(Ease.Linear)
    DOTween.Update(0.5)
    assert group.alpha == text.opacity == 0.5
    assert text.color == pytest.approx([0.5, 0, 0.5, 1])
    assert (image.width, image.height) == (150, 30)
    assert slider.value == 4 and not values
    assert S.DOValue(slider, 10, 1, snapping=True).target is slider
    DOTween.Update(1)
    assert slider.value == 10 and values[-1] == 10


def test_blendable_colors_use_one_creation_snapshot_and_preserve_external_color(target):
    image = UIImage()
    image.color = [0, 0, 0, 1]
    red = S.DOBlendableColor(image, [1, 0, 0, 1], 1).SetEase(Ease.Linear).SetAutoKill(False)
    green = S.DOBlendableColor(image, [0, 1, 0, 1], 1).SetEase(Ease.Linear).SetAutoKill(False)
    DOTween.Update(0.5)
    assert image.color == pytest.approx([0.5, 0.5, 0, 1])
    image.color = [0.5, 0.5, 0.2, 1]
    DOTween.Update(0.5)
    assert image.color == pytest.approx([1, 1, 0.2, 1])
    red.Rewind()
    assert image.color == pytest.approx([0, 1, 0.2, 1])
    green.Rewind()
    assert image.color == pytest.approx([0, 0, 0.2, 1])


def test_light_color_uses_the_native_rgba_property_shape(target):
    from infernux.components.builtin import Light
    light = target.game_object.add_component(Light)
    S.DOColor(light, (1, 0, 0), 1).SetEase(Ease.Linear)
    DOTween.Update(0.5)
    assert light.color == pytest.approx([1, 0.5, 0.5, 1])
    DOTween.Kill(light)
    light.color = [0, 0, 0, 1]
    S.DOBlendableColor(light, (1, 0, 0), 1).SetEase(Ease.Linear)
    DOTween.Update(0.5)
    assert light.color == pytest.approx([0.5, 0, 0, 1])
