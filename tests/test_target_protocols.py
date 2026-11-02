"""Optional target protocols drive live native properties through the shared clock."""
import pytest
from infernux.core.material import Material
from infernux.lib import InxMaterial, Vector2
from infernux.ui import UIImage
import infernux_tween as tween
from test_links import owner


class ScrollTarget:
    """A test scrolling owner publishes normalized coordinates into a UI pose."""

    def __init__(self, content):
        self.content = content

    @property
    def normalized_position(self):
        value = self.content.anchored_position
        return Vector2(-value.x / 100, value.y / 100)

    @normalized_position.setter
    def normalized_position(self, value):
        self.content.anchored_position = Vector2(-value.x * 100, value.y * 100)

    @property
    def horizontal_normalized_position(self):
        return self.normalized_position.x

    @horizontal_normalized_position.setter
    def horizontal_normalized_position(self, value):
        self.normalized_position = Vector2(value, self.normalized_position.y)

    @property
    def vertical_normalized_position(self):
        return self.normalized_position.y

    @vertical_normalized_position.setter
    def vertical_normalized_position(self, value):
        self.normalized_position = Vector2(self.normalized_position.x, value)


def test_normalized_pair_and_independent_axis_shortcuts_publish_native_ui_positions(owner):
    image = owner[1].add_component(UIImage)
    target = ScrollTarget(image)
    target.normalized_position = Vector2(0, 1)
    handle = tween.twn_normalized_pos(target, (.8, .2), 1).set_ease(tween.Ease.LINEAR)
    tween.update(.5)
    assert tuple(image.anchored_position) == pytest.approx((-40, 60), abs=1e-5)
    assert tween.pause(target) == 1 and not handle.is_playing()
    handle.kill()
    horizontal = tween.twn_horizontal_normalized_pos(target, 1, 1).set_ease(tween.Ease.LINEAR)
    vertical = tween.twn_vertical_normalized_pos(target, 0, 1).set_ease(tween.Ease.LINEAR)
    tween.update(.5)
    assert tuple(image.anchored_position) == pytest.approx((-70, 30), abs=1e-5)
    assert tween.kill(target) == 2
    assert not horizontal.is_active() and not vertical.is_active()


def test_exposed_float_shortcut_uses_real_native_parameter_storage_and_target_filters():
    material = Material(InxMaterial('Animated exposed parameter', 'Unlit'))
    material.set_float('test_gain', .25)
    handle = tween.twn_set_float(material, 'test_gain', 1, 1).set_ease(tween.Ease.LINEAR)
    try:
        material.set_float('test_gain', .5)
        handle.force_init()
        tween.update(.5)
        assert material.get_float('test_gain') == .75
        assert tween.kill(material) == 1 and not handle.is_active()
    finally:
        tween.clear()
