"""Material shortcuts resolve integer identifiers once when they are created."""
import pytest

from infernux.core.material import Material
from infernux.core.shader import Shader
from infernux.lib import InxMaterial, Vector2, vec4f
import infernux_tween as tween


@pytest.mark.parametrize('named', [False, True])
def test_scalar_and_vector_shortcuts_accept_property_ids_without_frame_resolution(named, monkeypatch):
    material = Material.create_lit()
    scalar = Shader.property_to_id('metallic')
    vector = Shader.property_to_id('metallicChannels')
    try:
        if named:
            tween.twn_float(material, 1., property_id=scalar, duration=1.).set_ease(tween.Ease.LINEAR)
            tween.twn_vector(material, vec4f(0, 1, 0, 0), property_id=vector, duration=1.).set_ease(tween.Ease.LINEAR)
        else:
            tween.twn_float(material, 1., scalar, 1.).set_ease(tween.Ease.LINEAR)
            tween.twn_vector(material, vec4f(0, 1, 0, 0), vector, 1.).set_ease(tween.Ease.LINEAR)
        def unexpected_resolution(*args):
            raise AssertionError('Playback must use its prepared property name')
        monkeypatch.setattr(Material, 'property_name', staticmethod(unexpected_resolution))
        tween.update(.5)
        assert material.get_float(scalar) == .5
        assert material.get_vector4(vector) == (.5, .5, 0., 0.)
    finally:
        tween.clear()
        material.dispose()


@pytest.mark.parametrize('shortcut', ['twn_float', 'twn_vector', 'twn_color', 'twn_fade', 'twn_blendable_color'])
def test_missing_material_ids_preserve_shortcut_missing_property_policy(shortcut):
    material = Material.create_lit()
    identifier = Shader.property_to_id('missingTweenProperty')
    end = vec4f() if shortcut == 'twn_vector' else [0., 0., 0., 1.] if 'color' in shortcut else .5
    try:
        assert getattr(tween, shortcut)(material, end, property_id=identifier, duration=1.) is None
        assert not material.has_property(identifier)
    finally:
        tween.clear()
        material.dispose()


@pytest.mark.parametrize('shortcut', ['twn_color', 'twn_fade', 'twn_blendable_color'])
def test_color_shortcuts_animate_the_same_property_selected_by_id(shortcut):
    material = Material.create_lit()
    identifier = Shader.property_to_id('baseColor')
    end = 0. if shortcut == 'twn_fade' else [0., 0., 0., 1.]
    try:
        material.set_color('baseColor', 1., 1., 1., 1.)
        getattr(tween, shortcut)(material, end, property_id=identifier, duration=1.).set_ease(tween.Ease.LINEAR)
        tween.update(.5)
        expected = (1., 1., 1., .5) if shortcut == 'twn_fade' else (.5, .5, .5, 1.)
        assert material.get_color(identifier) == expected
    finally:
        tween.clear()
        material.dispose()


def test_texture_id_tweens_keep_offset_and_tiling_independent(monkeypatch):
    native = InxMaterial('Texture tween IDs', 'Unlit')
    native.set_texture_guid('texSampler', '')
    material = Material(native)
    identifier = Shader.property_to_id('texSampler')
    try:
        tween.twn_offset(material, Vector2(1, 2), property_id=identifier, duration=1.).set_ease(tween.Ease.LINEAR)
        tween.twn_tiling(material, Vector2(3, 5), identifier, duration=1.).set_ease(tween.Ease.LINEAR)
        def unexpected_resolution(*args):
            raise AssertionError('Texture playback must use its prepared property name')
        monkeypatch.setattr(Material, 'property_name', staticmethod(unexpected_resolution))
        tween.update(.5)
        assert material.get_vector4('texSampler_ST') == (2., 3., .5, 1.)
    finally:
        tween.clear()
        material.dispose()
