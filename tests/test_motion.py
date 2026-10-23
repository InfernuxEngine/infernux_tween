import pytest

from infernux.lib import SceneManager, Vector3, quatf
from infernux_tween import Ease, LoopType, shortcuts as S
import infernux_tween as tween_api


@pytest.fixture
def target():
    manager = SceneManager.instance()
    scene = manager.create_scene("Procedural motion")
    obj = scene.create_game_object("Mover")
    yield obj.transform
    tween_api.clear()
    manager.unload_scene(scene)


def test_jump_has_multiple_arcs_and_exact_destination(target):
    tween = S.do_jump(target, (4, 2, 0), 3, 2, 1).set_auto_kill(False)
    tween.goto(0.25)
    assert tuple(target.position) == pytest.approx((1, 3.5, 0))
    tween.goto(0.5)
    assert tuple(target.position) == pytest.approx((2, 1, 0))
    tween.goto(1)
    assert tuple(target.position) == (4, 2, 0)
    tween.rewind()
    assert tuple(target.position) == (0, 0, 0)
    tween.kill()
    target.position = Vector3(2, 3, 0)
    relative = S.do_jump(target, (4, 2, 0), 3, 2, 1).set_relative()
    relative.complete()
    assert tuple(target.position) == (6, 5, 0)


def test_punch_and_shake_seek_without_accumulation(target):
    target.local_position = Vector3(5, 7, 9)
    for tween in (S.do_punch_position(target, (2, 0, 0), 1), S.do_shake_position(target, 1)):
        tween.set_relative().set_speed_based().set_loops(2, LoopType.INCREMENTAL).set_auto_kill(False)
        tween.force_init()
        assert tween.duration(False) == 1 and not tween._relative and not tween._speed_based
        tween.pause().goto(0.123)
        first = tuple(target.local_position)
        tween.goto(0.9).goto(0.123)
        assert tuple(target.local_position) == first
        tween.goto(1)
        assert tuple(target.local_position) == (5, 7, 9)
        tween.goto(1.123)
        assert tuple(target.local_position) == pytest.approx(first)
        tween.goto(2)
        assert tuple(target.local_position) == (5, 7, 9)
        tween.kill()

    from infernux.components.builtin import Camera
    from infernux_tween import ShakeRandomnessMode, TweenManager
    camera = target.game_object.add_component(Camera)
    camera_motion = S.do_shake_position(camera, 1).set_relative().set_speed_based().set_auto_kill(False)
    camera_motion.force_init()
    assert camera_motion.duration() == 1 and not camera_motion._relative and not camera_motion._speed_based
    camera_motion.goto(0.123)
    camera_offset = target.local_position - Vector3(5, 7, 9)
    camera_motion.kill()
    target.local_position = Vector3(5, 7, 9)
    transform_motion = S.do_shake_position(target, 1).set_auto_kill(False)
    transform_motion.goto(0.123)
    transform_offset = target.local_position - Vector3(5, 7, 9)
    assert tuple(camera_offset)[:2] == pytest.approx(tuple(transform_offset*3)[:2], abs=1e-5)
    assert camera_offset.z == 0
    transform_motion.kill()
    target.local_position = Vector3(5, 7, 9)
    rotated_camera = S.do_shake_position(camera, 1).set_auto_kill(False)
    target.local_rotation = quatf.euler(0, 90, 0)
    rotated_camera.goto(0.123)
    rotated_offset = target.local_position-Vector3(5, 7, 9)
    assert Vector3.dot(rotated_offset, target.forward) == pytest.approx(0, abs=1e-5)
    assert rotated_offset.magnitude == pytest.approx(camera_offset.magnitude)
    rotated_camera.kill()
    target.local_position = Vector3(5, 7, 9)
    vector_camera = S.do_shake_position(camera, 1, Vector3(2, 3, 4)).set_auto_kill(False)
    vector_camera.goto(0.123)
    assert abs(Vector3.dot(target.local_position-Vector3(5, 7, 9), target.forward)) > 0.1
    vector_camera.kill()
    target.local_rotation = quatf.identity()
    target.local_position = Vector3(5, 7, 9)
    harmonic = S.do_shake_position(target, 1, randomness_mode=ShakeRandomnessMode.HARMONIC).set_auto_kill(False)
    harmonic.goto(0.123)
    assert tuple(target.local_position) != pytest.approx(tuple(Vector3(5, 7, 9)+transform_offset))
    harmonic.kill()
    with pytest.raises(TypeError, match='ShakeRandomnessMode'):
        S.do_shake_position(target, 1, randomness_mode='Full')
    manager = TweenManager()
    values = [Vector3(0, 0, 0)]
    write = lambda value: values.__setitem__(0, value)
    assert manager.punch(lambda: values[0], write, Vector3(2, 0, 0), 0) is None
    assert manager.shake(lambda: values[0], write, 0) is None
    assert manager.total_active_tweens() == 0
    punch = manager.punch(lambda: values[0], write, Vector3(2, 0, 0), 1)
    punch.set_speed_based().force_init()
    assert punch.duration() == 1
    assert punch._owner is manager and tween_api.total_active_tweens() == 0
    manager.update(0.123)
    assert values[0].x != 0
    punch.complete()
    assert tuple(values[0]) == (0, 0, 0)
    shake = manager.shake(lambda: values[0], write, 1)
    shake.set_speed_based().force_init()
    assert shake.duration() == 1
    manager.update(0.123)
    assert values[0].z == 0
    shake.complete()
    assert tuple(values[0]) == (0, 0, 0)
    zero_duration = (
        S.do_punch_position(target, Vector3(2, 0, 0), 0),
        S.do_punch_rotation(target, Vector3(2, 0, 0), 0),
        S.do_punch_scale(target, Vector3(2, 0, 0), 0),
        tween_api.do_blendable_punch_rotation(target, Vector3(2, 0, 0), 0),
        S.do_shake_position(target, 0), S.do_shake_rotation(target, 0), S.do_shake_scale(target, 0),
        S.do_shake_position(camera, 0), S.do_shake_rotation(camera, 0),
    )
    assert all(item is None for item in zero_duration)
    assert tween_api.total_active_tweens() == 0


def test_blendable_displacements_preserve_external_motion_and_rewind_only_their_share(target):
    first = S.do_blendable_move_by(target, (4, 0, 0), 1).set_ease(Ease.LINEAR).set_auto_kill(False)
    second = S.do_blendable_move_by(target, (0, 6, 0), 1).set_ease(Ease.LINEAR).set_auto_kill(False)
    tween_api.update(0.5)
    assert tuple(target.position) == (2, 3, 0)
    target.position += Vector3(0, 0, 10)
    tween_api.update(0.5)
    assert tuple(target.position) == (4, 6, 10)
    first.rewind()
    assert tuple(target.position) == (0, 6, 10)
    second.rewind()
    assert tuple(target.position) == (0, 0, 10)


def test_spiral_seek_uses_authored_axis_and_contracts_back_to_its_origin(target):
    from infernux_tween import SpiralMode
    target.local_position = Vector3(2, 3, 4)
    tween = S.do_spiral(target, 2, (0, 0, 1), SpiralMode.EXPAND_THEN_CONTRACT).set_auto_kill(False)
    tween.goto(0.5)
    sampled = tuple(target.local_position)
    assert sampled != (2, 3, 4)
    tween.goto(2)
    assert tuple(target.local_position) == pytest.approx((2, 3, 4))
    tween.goto(0.5)
    assert tuple(target.local_position) == sampled
    tween.kill()
    target.local_position = Vector3(0, 0, 0)
    axial = S.do_spiral(target, 2, (1, 0, 0), depth=3).set_auto_kill(False)
    axial.goto(1)
    assert target.local_position.x == pytest.approx(1.5)
    assert target.local_position.y**2+target.local_position.z**2 == pytest.approx(1)


def test_blendable_rotation_keeps_other_tweens_and_external_orientation(target):
    from infernux.lib import quatf
    first = S.do_blendable_rotate_by(target, (0, 0, 180), 1).set_ease(Ease.LINEAR).set_auto_kill(False)
    second = S.do_blendable_rotate_by(target, (0, 0, 90), 1).set_ease(Ease.LINEAR).set_auto_kill(False)
    tween_api.update(0.5)
    assert quatf.angle(target.rotation, quatf.euler(0, 0, 135)) < 0.01
    target.rotation = quatf.euler(0, 0, 10)*target.rotation
    tween_api.update(0.5)
    assert quatf.angle(target.rotation, quatf.euler(0, 0, 280)) < 0.01
    first.rewind()
    second.rewind()
    assert quatf.angle(target.rotation, quatf.euler(0, 0, 10)) < 0.01
