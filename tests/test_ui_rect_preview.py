"""Editor preview restores canonical layout and temporary scene bindings."""
import pytest

from infernux.application import Application
from infernux.engine.interaction.previews import PreviewService
from infernux.lib import Vector2, Vector3
from infernux.ui import UIButton, UIImage
from infernux_tween import Ease
from runtime.TweenAnimation import AnimationType, TargetType, TweenAnimation
from test_links import owner
from test_ui_rect_transform import widget


def size_animation(image, end=(300, 120)):
    animation = image.game_object.add_component(TweenAnimation)
    animation.animation_type = AnimationType.SIZE
    animation.target, animation.target_type = image, TargetType.IMAGE
    animation.animation_valid = True
    animation.end_size, animation.ease = end, Ease.LINEAR
    return animation


@pytest.fixture(autouse=True)
def edit_mode(monkeypatch):
    monkeypatch.setattr(Application, 'is_headless', staticmethod(lambda: True))
    monkeypatch.setattr(PreviewService, '_instance', None)
    yield
    if PreviewService._instance is not None:
        PreviewService._instance.close()


def test_first_size_preview_restores_owner_ancestors_and_shared_visual_bindings(owner):
    canvas, image = widget(owner)
    button = image.game_object.add_component(UIButton)
    button.width, button.height = 90, 30
    before_canvas, before_pose = canvas.transform.serialize_document(), image.transform.serialize_document()
    before_image, before_button = image._serialize_fields_document(), button._serialize_fields_document()
    animation = size_animation(image)
    service = PreviewService()
    scope = service.begin('first rectangle preview')
    handle = animation.begin_preview(scope)
    animation._preview_manager.manual_update(.5, .5)
    assert image.width == button.width == 250
    assert image.transform._has_rect_layout and canvas.transform._has_rect_layout
    scope.close()
    assert not handle.is_active()
    assert image.transform.serialize_document() == before_pose
    assert canvas.transform.serialize_document() == before_canvas
    assert image._serialize_fields_document() == before_image
    assert button._serialize_fields_document() == before_button
    assert '_native_rect_layout' not in image.__dict__ and '_native_rect_layout' not in button.__dict__


def test_stretch_preview_restores_size_difference_and_keeps_parent_resize(owner):
    canvas, image = widget(owner)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta, image.anchored_position3d = Vector2(-20, -30), Vector3(12, 34, 3)
    animation = size_animation(image, (-40, -50))
    service = PreviewService()
    scope = service.begin('stretch rectangle preview')
    animation.begin_preview(scope)
    animation._preview_manager.manual_update(.5, .5)
    assert tuple(image.size_delta) == (-30, -40)
    canvas.reference_width = 1600
    scope.close()
    assert tuple(image.size_delta) == (-20, -30)
    assert tuple(image.anchored_position3d) == (12, 34, 3)
    assert image.width == 1580 and canvas.reference_width == 1600


def test_nested_unbound_layout_path_returns_to_authored_state(owner):
    canvas, image = widget(owner)
    parent_object = owner[0].create_game_object('Intermediate image')
    parent_object.set_parent(canvas.game_object, False)
    parent = parent_object.add_component(UIImage)
    parent.width, parent.height = 300, 200
    image.game_object.set_parent(parent_object, False)
    before = [target.transform.serialize_document() for target in (canvas, parent, image)]
    service = PreviewService()
    scope = service.begin('nested rectangle preview')
    animation = size_animation(image)
    animation.begin_preview(scope)
    animation._preview_manager.manual_update(.5, .5)
    scope.close()
    assert [target.transform.serialize_document() for target in (canvas, parent, image)] == before
    assert (parent.width, parent.height, image.width, image.height) == (300, 200, 200, 80)


def test_other_visual_cannot_claim_the_same_native_rectangle(owner):
    canvas, image = widget(owner)
    button = image.game_object.add_component(UIButton)
    service = PreviewService()
    first, second = service.begin('first'), service.begin('second')
    try:
        first.capture_rect_transform(image)
        with pytest.raises(RuntimeError, match='already owns'):
            second.capture_rect_transform(button)
    finally:
        second.close()
        first.close()


def test_editor_resolves_ui_move_to_anchored_position_and_preview_restores_it(owner):
    canvas, image = widget(owner)
    animation = image.game_object.add_component(TweenAnimation)
    animation.animation_type = AnimationType.MOVE
    animation.on_validate()
    assert animation.animation_valid and animation.target is image
    assert animation.target_type == TargetType.RECT_TRANSFORM
    before = image.transform.serialize_document()
    animation.end_vector, animation.ease = (120, -40, 12), Ease.LINEAR
    service = PreviewService()
    scope = service.begin('authored UI movement')
    animation.begin_preview(scope)
    start = tuple(image.anchored_position3d)
    animation._preview_manager.manual_update(.5, .5)
    assert tuple(image.anchored_position3d) == pytest.approx(tuple((a+b)/2 for a,b in zip(start,(120,-40,12))))
    scope.close()
    assert image.transform.serialize_document() == before


def test_temporary_parent_binding_cannot_be_used_by_an_independent_preview(owner):
    canvas, image = widget(owner)
    parent_object = owner[0].create_game_object('Temporarily bound preview parent')
    parent_object.set_parent(canvas.game_object, False)
    parent_object.add_component(UIImage)
    image.game_object.set_parent(parent_object, False)
    other_object = owner[0].create_game_object('Another image')
    other_object.set_parent(parent_object, False)
    other = other_object.add_component(UIImage)
    service = PreviewService()
    first, second = service.begin('first'), service.begin('second')
    try:
        animation = size_animation(image)
        animation.begin_preview(first)
        animation._preview_manager.manual_update(.1, .1)
        with pytest.raises(RuntimeError, match='rectangle parent'):
            second.capture_rect_transform(other)
    finally:
        second.close()
        first.close()


def test_independent_previews_share_the_permanent_canvas_frame(owner):
    canvas, image = widget(owner)
    other_object = owner[0].create_game_object('Another image')
    other_object.set_parent(canvas.game_object, False)
    other = other_object.add_component(UIImage)
    original = canvas.transform.serialize_document()
    service = PreviewService()
    first, second = service.begin('first'), service.begin('second')
    try:
        first.capture_rect_transform(image)
        second.capture_rect_transform(other)
        image.size_delta, other.size_delta = Vector2(10, 20), Vector2(30, 40)
        first.close()
        assert tuple(other.size_delta) == (30, 40)
        second.close()
        assert canvas.transform.serialize_document() == original
    finally:
        second.close()
        first.close()


def test_rendering_a_preview_does_not_materialize_unrelated_sibling_rectangles(owner):
    canvas, image = widget(owner)
    sibling_object = owner[0].create_game_object('Unchanged sibling')
    sibling_object.set_parent(canvas.game_object, False)
    sibling_object.add_component(UIImage)
    before = image.transform.serialize_document(), sibling_object.transform.serialize_document()
    service = PreviewService()
    scope = service.begin('temporary size')
    try:
        size_animation(image).begin_preview(scope)
        canvas._prepare_native_layout(None, 800, 600, 1)
        assert sibling_object.transform.serialize_document() == before[1]
    finally:
        scope.close()
    assert not canvas._prepare_native_layout(None, 800, 600, 1)
    assert image.transform.serialize_document() == before[0]
    assert sibling_object.transform.serialize_document() == before[1]


def test_native_document_undo_closes_preview_before_replaying_rectangle(owner, monkeypatch):
    from infernux.engine.undo import UndoManager, GenericComponentCommand
    monkeypatch.setattr(UndoManager, '_instance', None)
    manager = UndoManager()
    canvas, image = widget(owner)
    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
    image.size_delta = Vector2(-20, -30)
    before = image.transform.serialize_document()
    image.anchored_position3d = Vector3(12, 34, 3)
    after = image.transform.serialize_document()
    assert image.transform.deserialize_document(before)
    command = GenericComponentCommand(image.transform, before, after, 'Move UI rectangle', mergeable=False)
    assert manager.execute(command, raise_errors=True)
    service = PreviewService()
    scope = service.begin('undo during rectangle preview')
    animation = size_animation(image, (-40, -50))
    animation.begin_preview(scope)
    animation._preview_manager.manual_update(.5, .5)
    manager.undo()
    assert scope.closed and image.transform.serialize_document() == before
    assert animation.tween is None
    manager.redo()
    assert image.transform.serialize_document() == after


def test_preview_close_restores_an_existing_runtime_layout_driver(owner):
    canvas, image = widget(owner)
    canvas.rebuild_layout()
    layout = image.rect_transform
    layout._drive_rect(canvas.transform, Vector2(100, 40), Vector2(20, -10))
    before = image.transform.serialize_document()
    service = PreviewService()
    scope = service.begin('preview over published layout')
    animation = size_animation(image, (300, 120))
    animation.begin_preview(scope)
    animation._preview_manager.manual_update(.5, .5)
    assert tuple(layout.rect)[2:] != (100, 40)
    scope.close()
    assert layout._driver is canvas.transform
    assert tuple(layout.rect)[2:] == (100, 40)
    assert tuple(image.transform.local_position) == (20, -10, 0)
    assert image.transform.serialize_document() == before
