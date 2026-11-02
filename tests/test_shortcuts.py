import pytest

from infernux.lib import SceneManager, Vector2, Vector3, quatf, vec4f
from infernux.ui import UIButton, UIGroup, UIImage, UISlider, UIText
from infernux_tween import Ease, RotateMode, shortcuts as S
import infernux_tween as tween_api


@pytest.fixture
def target():
    scenes = SceneManager.instance()
    scene = scenes.create_scene("Tween shortcut contract")
    obj = scene.create_game_object("Animated target")
    try:
        yield obj.transform
    finally:
        tween_api.clear()
        scenes.unload_scene(scene)


def test_local_move_uniform_scale_and_filtered_target_control(target):
    target.local_position = Vector3(2, 4, 0)
    S.twn_local_move(target, (6, 8, 0), 1).set_ease(Ease.LINEAR)
    S.twn_scale(target, 2, 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert (target.local_position.x, target.local_position.y) == pytest.approx((4, 6))
    assert target.local_scale.x == pytest.approx(1.5)
    assert tween_api.pause(target) == 2
    tween_api.update(1)
    assert target.local_position.x == 4
    tween_api.restart(target)
    tween_api.update(1)
    assert target.local_position.x == 6 and target.local_scale.z == 2


def test_camera_aspect_tween_survives_render_viewport_updates_and_can_be_reset(target):
    from infernux.components.builtin import Camera
    camera = target.game_object.add_component(Camera)
    native = camera._require_cpp_component()
    native._update_automatic_aspect_ratio(2)
    S.twn_aspect(camera, 1, 1).set_ease(Ease.LINEAR)
    tween_api.update(.5)
    assert camera.aspect_ratio == 1.5
    native._update_automatic_aspect_ratio(3)
    assert camera.aspect_ratio == 1.5
    tween_api.update(.5)
    assert camera.aspect_ratio == 1
    camera.reset_aspect_ratio()
    assert camera.aspect_ratio == 3






def test_trail_shortcuts_reject_unrelated_hosts(target):
    with pytest.raises(TypeError, match="TrailRenderer"):
        S.twn_time(target, 2, 1)
    with pytest.raises(TypeError, match="TrailRenderer"):
        S.twn_resize(target, 2, 1, 1)


def test_texture_offset_and_tiling_overloads_preserve_each_other_and_other_slots():
    from infernux.core.material import Material
    from infernux.lib import InxMaterial
    native = InxMaterial("UV tween", "Unlit")
    native.set_texture_guid("texSampler", "")
    native.set_texture_guid("detail", "")
    material = Material(native)
    S.twn_offset(material, Vector2(1,2), 1).set_ease(Ease.LINEAR)
    S.twn_tiling(material, Vector2(3,5), duration=1).set_ease(Ease.LINEAR)
    S.twn_offset(material, Vector2(4,6), "detail", 1).set_ease(Ease.LINEAR)
    S.twn_tiling(material, Vector2(7,9), property="detail", duration=1).set_ease(Ease.LINEAR)
    tween_api.update(.5)
    assert material.get_vector4("texSampler_ST") == (2,3,.5,1)
    assert material.get_vector4("detail_ST") == (4,5,2,3)
    assert S.twn_offset(material, Vector2(1,1), "missing", 1) is None
    tween_api.clear()


def test_independent_axes_keep_other_values_and_snap_only_the_selected_axis(target):
    target.position = Vector3(1, 2, 3)
    S.twn_move_x(target, 8, 1, snapping=True).set_ease(Ease.LINEAR)
    S.twn_move_y(target, 10, 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert tuple(target.position) == pytest.approx((4, 6, 3))
    target.position = Vector3(target.position.x, target.position.y, 9)
    tween_api.update(0.25)
    assert tuple(target.position) == pytest.approx((6, 8, 9))


def test_euler_rotation_uses_shortest_route_or_explicit_turns(target):
    target.local_euler_angles = Vector3(0, 0, 170)
    short = S.twn_local_rotate(target, (0, 0, -170), 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert abs(target.local_euler_angles.z) == pytest.approx(180, abs=0.001)
    short.kill()
    target.local_euler_angles = Vector3(0, 0, 0)
    S.twn_local_rotate(target, (0, 0, 540), 1, RotateMode.FAST_BEYOND360).set_ease(Ease.LINEAR)
    tween_api.update(0.25)
    assert target.local_euler_angles.z == pytest.approx(135, abs=0.001)
    tween_api.update(0.25)
    assert target.local_euler_angles.z == pytest.approx(270, abs=0.001)


def test_ui_fade_color_size_and_slider_notification(target):
    group, text, image, button, slider = UIGroup(), UIText(), UIImage(), UIButton(), UISlider()
    text.color = [1, 0, 0, 1]
    image.color = [1, 1, 1, 1]
    image.width, image.height = 100, 20
    slider.minimum, slider.maximum = 0, 10
    values = []
    slider.on_value_changed.add_listener(values.append)
    S.twn_fade(group, 0, 1).set_ease(Ease.LINEAR)
    fade = S.twn_fade(text, end_value=0, duration=1).set_ease(Ease.LINEAR)
    S.twn_color(target=image, end_value=[0, 0, 1, 1], duration=1).set_ease(Ease.LINEAR)
    S.twn_color(button, [0, 0, 0, 1], 1).set_ease(Ease.LINEAR)
    S.twn_size_delta(image, Vector2(200, 40), 1).set_ease(Ease.LINEAR)
    S.twn_value(slider, 8, 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert group.alpha == text.color[3] == 0.5 and text.opacity == 1
    assert image.color == pytest.approx([0.5, 0.5, 1, 1])
    assert (image.width, image.height) == (150, 30)
    assert slider.value == 4 and values == [4]
    fade.change_end_value([0, 0, 0, 0.8])
    assert text.color == pytest.approx([1, 0, 0, 1])
    assert S.twn_value(slider, 10, 1, snapping=True).target is slider
    tween_api.update(1)
    assert slider.value == 10 and values[-1] == 10
    assert text.color == pytest.approx([1, 0, 0, 0.8])
    text.color = [0.2, 0.4, 0.6, 0.8]
    S.twn_fade(text, 0.1, 1).from_().set_ease(Ease.LINEAR)
    assert text.color == pytest.approx([0.2, 0.4, 0.6, 0.1])
    tween_api.update(0.5)
    assert text.color == pytest.approx([0.2, 0.4, 0.6, 0.45])


def test_axis_shortcuts_preserve_live_axes_and_from_snaps_all_initial_components(target):
    target.position = Vector3(1, 2.25, 3.75)
    move = S.twn_move_x(target, end_value=9, duration=1, snapping=True).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert tuple(target.position) == pytest.approx((5, 2.25, 3.75))
    move.change_end_value(Vector3(13, 100, 200))
    tween_api.update(0.5)
    assert tuple(target.position) == pytest.approx((7, 2.25, 3.75))
    S.twn_kill(target)
    target.position = Vector3(1, 2.25, 3.75)
    S.twn_move_x(target, 8.4, 1, snapping=True).from_().set_ease(Ease.LINEAR)
    # Real Vector3Plugin From snaps the whole initial value. Later constrained
    # updates preserve the other live components (typed reference fixture).
    assert tuple(target.position) == pytest.approx((8, 2, 4))
    tween_api.update(0.5)
    assert tuple(target.position) == pytest.approx((5, 2, 4))


def test_blendable_colors_use_one_creation_snapshot_and_preserve_external_color(target):
    image = UIImage()
    image.color = [0, 0, 0, 1]
    red = S.twn_blendable_color(image, [1, 0, 0, 1], 1).set_ease(Ease.LINEAR).set_auto_kill(False)
    green = S.twn_blendable_color(image, [0, 1, 0, 1], 1).set_ease(Ease.LINEAR).set_auto_kill(False)
    tween_api.update(0.5)
    assert image.color == pytest.approx([0.5, 0.5, 0, 1])
    image.color = [0.5, 0.5, 0.2, 1]
    tween_api.update(0.5)
    assert image.color == pytest.approx([1, 1, 0.2, 1])
    red.rewind()
    assert image.color == pytest.approx([0, 1, 0.2, 1])
    green.rewind()
    assert image.color == pytest.approx([0, 0, 0.2, 1])
    S.twn_kill(image)
    image.color = [0.2, 0, 0, 1]
    S.twn_blendable_color(target=image, end_value=[1, 0, 0, 1], duration=1).from_([0.5, 0, 0, 0]).set_ease(Ease.LINEAR)
    assert image.color == pytest.approx([0.7, 0, 0, 1])
    tween_api.update(0.5)
    assert image.color == pytest.approx([0.85, 0, 0, 1])
    S.twn_kill(image)
    image.color = [0, 0, 0, 1]
    tween_api.sequence().append(S.twn_blendable_color(image, [1, 0, 0, 1], 1).set_ease(Ease.LINEAR)).set_loops(
        2, tween_api.LoopType.INCREMENTAL)
    tween_api.update(1.5)
    assert image.color == pytest.approx([1.5, 0, 0, 1])


def test_light_color_uses_the_native_rgba_property_shape(target):
    from infernux.components.builtin import Light
    light = target.game_object.add_component(Light)
    S.twn_color(light, (1, 0, 0), 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert light.color == pytest.approx([1, 0.5, 0.5, 1])
    tween_api.kill(light)
    light.color = [0, 0, 0, 1]
    S.twn_blendable_color(light, (1, 0, 0), 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert light.color == pytest.approx([0.5, 0, 0, 1])


def test_camera_clipping_and_tween_time_scale_use_real_native_properties(target):
    from infernux.components.builtin import Camera
    camera = target.game_object.add_component(Camera)
    camera.near_clip, camera.far_clip = 0.2, 100
    S.twn_near_clip_plane(camera, end_value=1, duration=1).set_ease(Ease.LINEAR)
    S.twn_far_clip_plane(camera, end_value=500, duration=1).set_ease(Ease.LINEAR)
    animated = S.twn_move(target, Vector3(10, 0, 0), 4).set_ease(Ease.LINEAR)
    speed = S.twn_time_scale(animated, end_value=0, duration=1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert (camera.near_clip, camera.far_clip) == pytest.approx((0.6, 300))
    assert animated.time_scale == 0.5 and speed.target is animated
    S.twn_kill(animated)
    assert not speed.is_active() and animated.is_active()


def test_look_at_captures_on_start_and_dynamic_look_at_recomputes_world_direction(target):
    destination = Vector3(10, 0, 0)
    fixed = S.twn_look_at(target, towards=destination, duration=1).set_ease(Ease.LINEAR)
    target.position = Vector3(0, 0, 10)
    tween_api.update(0.5)
    assert target.euler_angles.y == pytest.approx(67.5, abs=0.001)
    target.position = Vector3(0, 0, 0)
    tween_api.update(0.5)
    assert target.euler_angles.y == pytest.approx(135, abs=0.001)
    assert not fixed.is_active()
    target.rotation = quatf.identity()
    S.twn_dynamic_look_at(target, destination, 1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert target.euler_angles.y == pytest.approx(45, abs=0.001)
    target.position = Vector3(0, 0, 10)
    tween_api.update(0.5)
    assert tuple(target.forward) == pytest.approx((2**-0.5, 0, -2**-0.5), abs=0.001)
    target.rotation = quatf.identity()
    S.twn_look_at(target, Vector3(10, 10, 0), 1, tween_api.AxisConstraint.Y).set_ease(Ease.LINEAR)
    tween_api.update(1)
    assert target.forward.y == pytest.approx(0, abs=0.001)
    S.twn_look_at(target, target.position+Vector3(0, 1, 0), 1).set_ease(Ease.LINEAR)
    tween_api.update(1)
    assert tuple(target.forward) == pytest.approx((0, 1, 0), abs=0.001)
    S.twn_look_at(target, target.position, 1).set_ease(Ease.LINEAR)
    tween_api.update(1)
    assert abs(quatf.dot(target.rotation, quatf.identity())) == pytest.approx(1, abs=0.001)


def test_material_overloads_vector_and_missing_property_do_not_invent_shader_fields(target):
    from infernux.core.material import Material
    material = Material.create_lit()
    try:
        S.twn_color(material, end_value=[0, 0, 0, 1], duration=1).set_ease(Ease.LINEAR)
        S.twn_color(material, [1, 0, 0, 1], "emissionColor", 1).set_ease(Ease.LINEAR)
        S.twn_float(material, end_value=1, property="metallic", duration=1).set_ease(Ease.LINEAR)
        S.twn_vector(material, end_value=vec4f(0, 1, 0, 0), property="metallicChannels", duration=1).set_ease(Ease.LINEAR)
        tween_api.update(0.5)
        assert material.get_color("baseColor") == pytest.approx((0.5, 0.5, 0.5, 1))
        assert material.get_color("emissionColor") == pytest.approx((0.5, 0, 0, 0.5))
        assert material.get_float("metallic") == 0.5
        assert material.get_vector4("metallicChannels") == pytest.approx((0.5, 0.5, 0, 0))
        S.twn_kill(material)
        S.twn_fade(target=material, end_value=0, property="emissionColor", duration=1).set_ease(Ease.LINEAR)
        tween_api.update(0.5)
        assert material.get_color("emissionColor") == pytest.approx((0.5, 0, 0, 0.25))
        assert S.twn_color(material, [0]*4, "not_a_shader_property", 1) is None
        assert S.twn_float(material, 3, "not_a_shader_property", 1) is None
        assert S.twn_vector(material, vec4f(), "not_a_shader_property", 1) is None
        assert not material.has_property("not_a_shader_property")
        with pytest.raises(TypeError):
            S.twn_color(material, [0]*4, True, 1)
    finally:
        S.twn_kill(material)
        material.dispose()


def test_gradient_sequence_uses_native_keys_without_changing_alpha_and_line_color2(target):
    from infernux.components.builtin import LineRenderer
    from infernux.graph.ramp import Gradient, GradientKey
    image = UIImage()
    image.color = [0, 0, 0, 0.25]
    gradient = Gradient((GradientKey(0, (1, 0, 0, 0)), GradientKey(0.5, (0, 1, 0, 0.8)),
                         GradientKey(0.75, (0, 0, 1, 0.6))))
    sequence = S.twn_gradient_color(target=image, gradient=gradient, duration=2)
    assert isinstance(sequence, tween_api.Sequence) and sequence.duration() == 2
    assert image.color == pytest.approx([1, 0, 0, 0.25])
    line = target.game_object.add_component(LineRenderer)
    start = S.Color2([1, 0, 0, 1], [0, 1, 0, 0.5])
    end = S.Color2([0, 0, 1, 0.5], [1, 0, 0, 1])
    S.twn_color(line, start_value=start, end_value=end, duration=1).set_ease(Ease.LINEAR)
    tween_api.update(0.5)
    assert image.color == pytest.approx([0.5, 0.5, 0, 0.25])
    assert line.start_color == pytest.approx([0.5, 0, 0.5, 0.75])
    assert line.end_color == pytest.approx([0.5, 0.5, 0, 0.75])
    tween_api.update(1)
    assert image.color == pytest.approx([0, 0.5, 0.5, 0.25])


def test_target_controls_and_culture_grouping_preserve_real_playback_state(target):
    text = UIText()
    S.twn_counter(text, from_value=0, end_value=1234567, duration=1,
                 culture=S.CultureInfo(" ", (3, 2))).set_ease(Ease.LINEAR)
    assert S.twn_complete(text) == 1 and text.text == "12 34 567"
    move = S.twn_move(target, Vector3(10, 0, 0), 1).set_auto_kill(False).set_ease(Ease.LINEAR)
    assert S.twn_pause(target) == 1
    assert S.twn_play(target) == 1
    assert S.twn_goto(target, to=0.5) == 1 and target.position.x == 5
    assert S.twn_rewind(target, include_delay=False) == 1 and target.position.x == 0
    assert S.twn_restart(target, include_delay=False) == 1
    tween_api.update(0.25)
    assert target.position.x == 2.5
    assert S.twn_flip(target) == 1
    tween_api.update(0.25)
    assert target.position.x == 0
    assert S.twn_toggle_pause(target) == 0 and not move.is_playing()
    assert S.twn_play_forward(target) == 1
    tween_api.update(0.5)
    assert S.twn_play_backwards(target) == 1
    assert S.twn_smooth_rewind(target) == 1
    tween_api.update(0.25)
    assert target.position.x == 2.5
    assert S.twn_kill(target) == 1 and not move.is_active()
