"""Read rendered pixels and pointer hits after native rectangle animation."""
import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
import infernux as inx
from infernux.lib import SceneManager, Vector2, Vector3
from infernux.ui import UICanvas, UIImage
from infernux.batch import batch_write
import infernux_tween as tween


class AnchorPipeline(inx.renderstack.RenderPipeline):
    name = 'UI anchor acceptance'

    def define_topology(self, graph):
        color = graph.create_texture('color', camera_target=True)
        graph.add_pass('Clear').write_color(color).set_clear(color=(0, 0, 0, 1))
        graph.screen_ui_overlay_section()
        graph.set_output(color)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    # Independent pixel-space predictions, not values read from get_rect().
    expected_rects = [(41., 38., 48., 24.), (30., 22.5, 100., 75.), (80., 60., 40., 24.)]
    proof = []
    with tempfile.TemporaryDirectory(prefix='infernux-anchor-gpu-') as folder:
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
            canvas_owner = scene.create_game_object('Canvas')
            canvas = canvas_owner.add_component(UICanvas)
            canvas.reference_width, canvas.reference_height = 160, 120
            image_owner = scene.create_game_object('Image')
            image_owner.set_parent(canvas_owner, False)
            image = image_owner.add_component(UIImage)
            image.color = [1, 0, 0, 1]
            frontend.set_render_pipeline(pipeline)
            native.set_game_camera_enabled(True)
            native.set_play_mode_rendering(True)
            phase = frame_count = changed = 0
            ticket = None

            def configure():
                tween.clear()
                image.anchor_min = image.anchor_max = Vector2(.5, .5)
                image.pivot = Vector2(.5, .5)
                image.size_delta = Vector2(48, 24)
                image.anchored_position3d = Vector3(0, 0, 0)
                if phase == 0:
                    tween.twn_anchor_pos(image, Vector2(-30, 20), 1).set_ease(tween.Ease.LINEAR).goto(.5)
                elif phase == 1:
                    image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
                    image.size_delta = Vector2(-80, -60)
                    tween.twn_size_delta(image, Vector2(-40, -30), 1).set_ease(tween.Ease.LINEAR).goto(.5)
                else:
                    batch_write([image], np.asarray([40.], dtype=np.float64), 'width')
                    batch_write([image], np.asarray([[0., 1.]], dtype=np.float32), 'pivot')

            configure()

            def after_draw():
                nonlocal phase, frame_count, changed, ticket, finished
                frame_count += 1
                try:
                    if ticket is None and frame_count >= changed + 7:
                        ticket = frontend.request_render_target_readback(True)
                    elif ticket is not None and ticket.done:
                        assert not ticket.error, ticket.error
                        pixels = ticket.result_numpy()[..., :3]
                        x, y, width, height = expected_rects[phase]
                        yy, xx = np.mgrid[:120, :160]
                        dx, dy = xx + .5 - x, yy + .5 - y
                        inside = (dx >= 0) & (dx <= width) & (dy >= 0) & (dy <= height)
                        valid = np.minimum.reduce([abs(dx), abs(dx - width), abs(dy), abs(dy - height)]) > 1.25
                        expected = np.zeros_like(pixels)
                        expected[..., 0] = inside
                        np.testing.assert_allclose(pixels[valid], expected[valid], atol=.01)
                        hits = 0
                        for iy in range(3, 120, 7):
                            for ix in range(3, 160, 7):
                                if valid[iy, ix]:
                                    assert (canvas.raycast(ix + .5, iy + .5) is image) == bool(inside[iy, ix])
                                    hits += 1
                        proof.append(dict(rect=expected_rects[phase], pixels=int(valid.sum()), pointer_samples=hits))
                        phase += 1
                        ticket, changed = None, frame_count
                        if phase == len(expected_rects):
                            finished = True
                            native.exit()
                        else:
                            configure()
                    assert frame_count < 120, 'Anchor GPU check did not finish'
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
    print('PASS three native rectangle animation, GPU and pointer phases')


if __name__ == '__main__':
    main()
