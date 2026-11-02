"""Convert authored rectangle centres without editing the source layout."""
import pytest
from infernux.lib import Vector2, Vector3
from infernux.ui import UICanvas, UIImage
from infernux_tween import switch_to_rect_transform
from test_links import owner


@pytest.mark.parametrize('world', (False, True))
def test_conversion_aligns_centres_in_screen_and_world_units_without_implicit_writes(owner, world):
    scene, root = owner
    if world:
        parent = root.add_component(UIImage)
        parent.width, parent.height = 800, 600
    else:
        canvas = root.add_component(UICanvas)
        canvas.reference_width, canvas.reference_height = 800, 600
    widgets = []
    for name, size, pivot, position in (
        ('Source', (20, 10), (0, 1), (10, 20)),
        ('Target', (40, 20), (.75, .25), (100, 50)),
    ):
        obj = scene.create_game_object(name)
        obj.set_parent(root, False)
        widget = obj.add_component(UIImage)
        widget.anchor_min = widget.anchor_max = Vector2(.5, .5)
        widget.size_delta, widget.pivot = Vector2(*size), Vector2(*pivot)
        widget.anchored_position = Vector2(*position)
        widgets.append(widget)
    source, target = widgets
    documents = tuple(w.game_object.serialize_document() for w in widgets)
    position = switch_to_rect_transform(source, target)
    assert tuple(position) == pytest.approx((30, 10), abs=2e-5)
    assert documents == tuple(w.game_object.serialize_document() for w in widgets)
    target.anchored_position = position

    def centre(widget):
        rect = widget.rect_transform
        return widget.transform.transform_point(Vector3(
            (rect.rect.z * (.5 - rect.pivot.x)) * rect._position_scale,
            (rect.rect.w * (.5 - rect.pivot.y)) * rect._position_scale,
            0,
        ))

    assert tuple(centre(target)) == pytest.approx(tuple(centre(source)), abs=2e-5)
