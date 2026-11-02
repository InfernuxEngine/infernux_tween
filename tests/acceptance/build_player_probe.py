"""Cook an installed Tween package and verify its standalone Player output."""
import argparse
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


@contextmanager
def authored_project(args, *, bootstrap_source=None):
    import infernux as inx
    from infernux.components.script_loader import load_and_create_component
    from infernux.engine import SceneFileManager
    from infernux.engine.library_sync import sync_resources
    from infernux.engine.player_build_preflight import publish_player_asset_catalog
    from infernux.lib import RuntimeMode, SceneManager
    from infernux.plugins import PluginManager
    from infernux.resources import activate_library

    shutil.copytree(args.fixture, args.project)
    shutil.copy2(bootstrap_source or Path(__file__).parent / 'player/Bootstrap.py',
                 args.project / 'Assets/Scripts/Bootstrap.py')
    os.environ['INFERNUX_PACKAGE_CACHE_ROOT'] = str(args.project / 'Cache/PackageLibrary')
    sync_resources(str(args.project))
    activate_library(str(args.project))
    engine = inx.Engine(mode=RuntimeMode.Headless)
    packages = None
    try:
        engine.init_headless(str(args.project))
        packages = PluginManager(str(args.project), engine=engine, runtime=False)
        state = packages.install_package(str(args.package), install_dependencies=False)
        assert state.loaded and not state.error, state.error
        api = importlib.import_module('infernux_tween')
        assert Path(api.__file__).is_relative_to(args.project / 'Packages')
        engine.get_asset_database().refresh()
        assert inx.SceneManager.load_scene(str(args.project / 'Assets/Scenes/Main.scene'))
        scene_files = SceneFileManager.instance()
        deadline = time.monotonic() + 30
        while scene_files.is_loading and time.monotonic() < deadline:
            engine.tick(0)
            time.sleep(.001)
        assert not scene_files.is_loading, scene_files.last_scene_load
        assert scene_files.last_scene_load['status'] == 'loaded', scene_files.last_scene_load
        scene = SceneManager.instance().get_active_scene()
        script = args.project / 'Packages/infernux/tween/runtime/TweenAnimation.py'
        animation = load_and_create_component(str(script), asset_database=engine.get_asset_database(),
                                              type_name='TweenAnimation')
        module = sys.modules[type(animation).__module__]
        authored = scene.create_game_object('Cooked Tween authoring probe')
        authored.add_py_component(animation)
        animation.animation_type = module.AnimationType.LOCAL_MOVE
        animation.target_type = module.TargetType.TRANSFORM
        animation.target = authored.transform
        animation.animation_valid = True
        animation.end_vector = (0., 2., 0.)
        animation.duration, animation.ease = .3, api.Ease.LINEAR
        canvas = scene.create_game_object('Cooked authored Canvas').add_component(inx.UICanvas)
        canvas.reference_width, canvas.reference_height = 640, 360
        ui_object = scene.create_game_object('Cooked Tween UI rectangle')
        ui_object.set_parent(canvas.game_object, False)
        image = ui_object.add_component(inx.UIImage)
        image.enabled = False
        image.anchor_min, image.anchor_max = inx.Vector2(0, 0), inx.Vector2(1, 1)
        image.size_delta, image.anchored_position = inx.Vector2(-20, -30), inx.Vector2(0, 0)
        ui_animation = ui_object.add_component(type(animation))
        ui_animation.animation_type = module.AnimationType.SIZE
        ui_animation.target_type, ui_animation.target = module.TargetType.IMAGE, image
        ui_animation.animation_valid = True
        ui_animation.end_size = (-40., -50.)
        ui_animation.duration, ui_animation.ease = .3, api.Ease.LINEAR
        SceneFileManager.instance().mark_dirty()
        assert SceneFileManager.instance().save_current_scene()
        catalog = publish_player_asset_catalog(str(args.project), engine.get_asset_database())
        yield catalog
    finally:
        if packages is not None:
            packages.shutdown()
        engine.exit()


def cook(args):
    from infernux.engine.game_builder import GameBuilder

    with authored_project(args) as catalog:
        builder = GameBuilder(str(args.project), str(args.output), game_name='InfernuxTweenProbe',
                              display_mode='windowed', window_width=640, window_height=360,
                              debug_mode=False, lto=True, include_jit_runtime=False,
                              player_runtime_root=str(args.runtime))
        builder.freeze_asset_index_entries(catalog['entries'], runtime_type_records=catalog['runtime_type_records'])
        return Path(builder.build(on_progress=lambda message, fraction: print(message, flush=True)))


def run_player(args, result):
    executable = result / ('InfernuxTweenProbe.exe' if sys.platform == 'win32' else 'InfernuxTweenProbe')
    state_root = Path(tempfile.mkdtemp(prefix=args.output.name + '-state-', dir=args.output.parent))
    environment = {key: value for key, value in os.environ.items()
                   if key not in ('PYTHONPATH', 'PYTHONHOME', 'INFERNUX_NATIVE_MODULE_DIR', 'LD_LIBRARY_PATH')
                   and not key.startswith('_INFERNUX_PLAYER_')}
    environment.update(LOCALAPPDATA=str(state_root), XDG_STATE_HOME=str(state_root), SDL_AUDIODRIVER='dummy')
    log_path = args.proof.with_suffix('.player.log')
    with log_path.open('w', encoding='utf8') as log:
        process = subprocess.Popen([str(executable)], cwd=result, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        try:
            code = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise AssertionError(f'Player timed out; see {log_path}')
    assert code == 0, f'Player exited with {code}; see {log_path}'
    player_proof = state_root / 'Infernux/Players/InfernuxTweenProbe/Data/tween-player-proof.json'
    proof = json.loads(player_proof.read_text(encoding='utf8'))
    assert proof['passed'] and proof['player'], proof
    assert Path(proof['library_origin']).is_relative_to(state_root)
    assert 'Packages/infernux/tween' in proof['library_origin'].replace('\\', '/')
    assert Path(proof['native_origin']).parent.samefile(result / 'InfernuxTweenProbe_Data/Runtime/infernux/lib')
    image_path = player_proof.with_name('tween-player.png')
    verify_player_image(proof, image_path)
    proof.update(executable=str(executable), player_log=str(log_path), screenshot=str(image_path))
    args.proof.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf8')
    print('PASS cooked Player: package loading, authored components, native clocks, physics and rendered UI')


def player_ui_geometry(width, height):
    from math import ceil, sqrt

    # Fixture canvas: 640x360, width/height match 0.5. The green 80x40
    # rectangle is center-anchored at (60,20); the blue sibling is at (32,32).
    scale = sqrt((width / 640) * (height / 360))
    center = width / 2 + 60 * scale, height / 2 - 20 * scale
    edges = (width / 2 + 20 * scale, height / 2 - 40 * scale,
             width / 2 + 100 * scale, height / 2)
    # Pixel centers lie at n+0.5, and the lower/right edges are exclusive.
    bounds = tuple(ceil(edge - .5) for edge in edges)
    return scale, bounds, tuple(round(value) for value in center), (round(32 * scale), round(32 * scale))


def verify_player_image(proof, image_path):
    from PIL import Image, ImageChops
    import numpy as np

    with Image.open(image_path).convert('RGB') as image:
        width, height = image.size
        scale, expected, (x, y), static_center = player_ui_geometry(width, height)
        red, green, blue = image.getpixel((x, y))
        assert green > 220 and red < 25 and blue < 25, (image.size, (red, green, blue))
        channels = image.split()
        masks = [channels[index].point(lambda value: 255 if value < 25 else 0) for index in (0, 2)]
        masks.append(channels[1].point(lambda value: 255 if value > 220 else 0))
        bounds = ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2]).getbbox()
        assert bounds == expected, (bounds, expected)
        static_pixel = image.getpixel(static_center)
        assert static_pixel[2] > 220 and max(static_pixel[:2]) < 25, static_pixel
        proof['rendered_size'] = image.size
        proof['animated_rectangle_bounds'] = bounds
        proof['unchanged_sibling_center'] = static_pixel
        proof['animated_rectangle_center'] = (red, green, blue)
        proof['canvas_scale'] = scale
        pixels = np.asarray(image)
        yellow = (pixels[:, :, 0] > 180) & (pixels[:, :, 1] > 180) & (pixels[:, :, 2] < 80)
        bands = []
        for row in np.flatnonzero(yellow.any(axis=1)):
            if not bands or row > bands[-1][-1][0] + 1:
                bands.append([])
            bands[-1].append((int(row), int(np.flatnonzero(yellow[row])[-1])))
        if len(bands) != 2:
            raise RuntimeError(f'Expected two rendered font lines, got {len(bands)}')
        marker_columns = [max(column for _, column in band) for band in bands]
        if abs(marker_columns[0] - marker_columns[1]) > 1:
            raise RuntimeError(f'Rendered CJK/Latin columns differ: {marker_columns}')
        proof['font_marker_pixel_columns'] = marker_columns
        proof['font_pixels_verified'] = True
        proof['image_verified'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixture', 'package', 'project', 'runtime', 'output', 'proof'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-only', action='store_true', help='Verify an already cooked --output directory.')
    args = parser.parse_args()
    for name in ('fixture', 'package', 'project', 'runtime', 'output', 'proof'):
        setattr(args, name, getattr(args, name).resolve())
    args.proof.parent.mkdir(parents=True, exist_ok=True)
    run_player(args, args.output if args.run_only else cook(args))


if __name__ == '__main__':
    main()
