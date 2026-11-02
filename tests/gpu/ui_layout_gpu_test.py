"""Check automatic layout against independent GPU pixels, picking and scene data."""
import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
import infernux as inx
from infernux.lib import SceneManager
from infernux.ui import UICanvas, UIFrame, UIImage, UILayoutDirection, UILayoutElement
import infernux_tween as tween
from ui_anchor_gpu_test import AnchorPipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    rectangles = [((30, 25, 30, 20), (70, 25, 40, 20)),
                  ((30, 25, 40, 20), (80, 25, 40, 20)),
                  ((65, 40, 30, 20), (60, 40, 40, 20))]
    proof = []
    with tempfile.TemporaryDirectory(prefix='infernux-layout-gpu-') as folder:
        root = Path(folder)
        (root / 'Assets').mkdir()
        (root / 'ProjectSettings').mkdir()
        frontend = inx.Engine()
        native = frontend.get_native_engine()
        pipeline = AnchorPipeline()
        errors, finished = [], False
        try:
            frontend.init_renderer(160, 120, folder)
            frontend.resize_game_render_target(160, 120)
            native.set_scene_view_visible(False)
            native.set_editor_fps_cap(240)
            native.set_editor_idle_fps(0)
            scene = SceneManager.instance().get_active_scene()
            for obj in scene.get_root_objects():
                scene.destroy_game_object(obj)
            scene.create_game_object('Camera').add_component(inx.Camera)
            canvas = scene.create_game_object('Canvas').add_component(UICanvas)
            canvas.reference_width, canvas.reference_height = 160, 120
            frame_owner = scene.create_game_object('Flow')
            frame_owner.set_parent(canvas.game_object, False)
            frame = frame_owner.add_component(UIFrame)
            frame.set_rect(20, 20, 120, 60, 160, 120)
            frame.layout_direction, frame.gap = UILayoutDirection.Horizontal, 10
            frame.padding_left, frame.padding_top = 10, 5
            images = []
            for index, width in enumerate((30, 40)):
                obj = scene.create_game_object('Item ' + str(index))
                obj.set_parent(frame_owner, False)
                image = obj.add_component(UIImage)
                image.width, image.height = width, 20
                image.color = [1, 0, 0, 1] if index == 0 else [0, 0, 1, 1]
                images.append(image)
            sizing = images[0].game_object.add_component(UILayoutElement)
            sizing.preferred_width = 30
            for element in (frame, *images):
                _ = element.rect_transform
            frontend.set_render_pipeline(pipeline)
            native.set_game_camera_enabled(True)
            native.set_play_mode_rendering(True)
            phase = frame_count = changed = 0
            ticket = None
            document = canvas.game_object.serialize_document()

            def after_draw():
                nonlocal phase, frame_count, changed, ticket, finished, document
                frame_count += 1
                try:
                    if ticket is None and frame_count >= changed + 7:
                        ticket = frontend.request_render_target_readback(True)
                    elif ticket is not None and ticket.done:
                        assert not ticket.error, ticket.error
                        pixels = ticket.result_numpy()[..., :3]
                        yy, xx = np.mgrid[:120, :160]
                        expected = np.zeros_like(pixels)
                        valid = np.ones((120, 160), dtype=bool)
                        owners = np.full((120, 160), -1)
                        for index, (x, y, width, height) in enumerate(rectangles[phase]):
                            dx, dy = xx + .5 - x, yy + .5 - y
                            inside = (dx >= 0) & (dx <= width) & (dy >= 0) & (dy <= height)
                            valid &= np.minimum.reduce([abs(dx), abs(dx-width), abs(dy), abs(dy-height)]) > 1.25
                            expected[inside] = [1, 0, 0] if index == 0 else [0, 0, 1]
                            owners[inside] = index
                        np.testing.assert_allclose(pixels[valid], expected[valid], atol=.01)
                        samples = 0
                        for iy in range(3, 120, 7):
                            for ix in range(3, 160, 7):
                                if valid[iy, ix]:
                                    hit = canvas.raycast(ix + .5, iy + .5)
                                    index = owners[iy, ix]
                                    assert (hit is images[index]) if index >= 0 else hit not in images
                                    samples += 1
                        current_document = canvas.game_object.serialize_document()
                        if current_document != document:
                            args.proof.with_suffix('.before.json').write_text(json.dumps(document, indent=2), encoding='utf8')
                            args.proof.with_suffix('.after.json').write_text(json.dumps(current_document, indent=2), encoding='utf8')
                            raise AssertionError('Runtime layout changed the authored scene document')
                        proof.append(dict(rectangles=rectangles[phase], pixels=int(valid.sum()),
                                          pointer_samples=samples, authoring_unchanged=True))
                        phase += 1
                        ticket, changed = None, frame_count
                        if phase == len(rectangles):
                            finished = True
                            native.exit()
                        elif phase == 1:
                            tween.twn_preferred_size(sizing, (50, -1), 1).set_ease(tween.Ease.LINEAR).goto(.5)
                            document = canvas.game_object.serialize_document()
                        else:
                            tween.clear()
                            frame.layout_direction = UILayoutDirection.None_
                            document = canvas.game_object.serialize_document()
                    assert frame_count < 120, 'Layout GPU check did not finish'
                except BaseException as error:
                    errors.append(error)
                    native.exit()

            native.set_post_draw_callback(after_draw)
            native.run()
            if errors:
                raise errors[0]
            assert finished
        finally:
            tween.clear()
            native.set_post_draw_callback(None)
            frontend.set_render_pipeline(None)
            pipeline.dispose()
            native.cleanup()
    args.proof.write_text(json.dumps(dict(passed=True, phases=proof), indent=2) + '\n', encoding='utf8')
    print('PASS automatic Flow, preferred-size animation and released layout GPU/picking phases')


if __name__ == '__main__':
    main()
