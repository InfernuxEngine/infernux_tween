"""Install the package and exercise automatic Tween clocks and live contacts."""
import argparse
import importlib
import json
import os
from pathlib import Path
import tempfile

import infernux as inx
from infernux.lib import RuntimeMode, SceneManager, Vector3
from infernux.plugins import PluginManager
from infernux.runtime_services import _update_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    observations = []
    with tempfile.TemporaryDirectory(prefix='infernux-tween-runtime-') as folder:
        root = Path(folder)
        (root / 'Assets').mkdir()
        (root / 'ProjectSettings').mkdir()
        os.environ['INFERNUX_PACKAGE_CACHE_ROOT'] = str(root / 'Cache/PackageLibrary')
        engine = inx.Engine(mode=RuntimeMode.Headless)
        packages = None
        scenes = SceneManager.instance()
        try:
            engine.init_headless(folder)
            packages = PluginManager(folder, engine=engine, runtime=True)
            installed = packages.install_package(str(args.package.resolve()), install_dependencies=False)
            assert installed.loaded and not installed.error, installed.error
            api = importlib.import_module('infernux_tween')
            assert Path(api.__file__).is_relative_to(root / 'Packages')
            scene = scenes.create_scene('Automatic Tween physics')
            scenes.set_active_scene(scene)
            scenes.set_fixed_time_step(.02)
            obj = scene.create_game_object('Kinematic pusher')
            obj.transform.position = Vector3(-2, 0, 0)
            obj.add_component(inx.BoxCollider)
            body = obj.add_component(inx.Rigidbody)
            body.is_kinematic, body.use_gravity = True, False
            ball = scene.create_game_object('Dynamic contact receiver')
            ball.add_component(inx.SphereCollider).radius = .4
            receiver = ball.add_component(inx.Rigidbody)
            receiver.use_gravity = False
            scenes.play()
            engine.tick(0)
            fixed_start = scenes.fixed_time
            values, completions = [0., 0.], []
            motion = api.twn_move(body, Vector3(2, 0, 0), 1).set_ease(api.Ease.LINEAR).set_auto_kill(False)
            motion.set_update(api.UpdateType.FIXED)
            motion.on_complete(lambda: completions.append('body'))
            for index, independent in enumerate((False, True)):
                api.to(lambda i=index: values[i], lambda value, i=index: values.__setitem__(i, value), 1., 1.) \
                    .set_ease(api.Ease.LINEAR).set_update(api.UpdateType.NORMAL, independent) \
                    .set_auto_kill(False).on_complete(lambda i=index: completions.append(str(i)))

            def advance(count, label, expected_time, expected_independent):
                for _ in range(count):
                    engine.tick(.02)
                elapsed_fixed = scenes.fixed_time - fixed_start
                expected_x = -2 + 4 * min(elapsed_fixed, 1.)
                assert abs(body.position.x - expected_x) < 3e-5, (label, tuple(body.position), expected_x, motion.position,
                                                                elapsed_fixed, values)
                assert max(abs(a-b) for a,b in zip(body.position, body.transform.position)) < 3e-5
                assert abs(values[0] - min(expected_time, 1.)) < 3e-6, (label, values)
                assert abs(values[1] - min(expected_independent, 1.)) < 3e-6, (label, values)
                observations.append(dict(stage=label, body_position=tuple(body.position),
                                         fixed_elapsed=elapsed_fixed,
                                         dynamic_position=tuple(receiver.position), values=list(values)))

            advance(20, 'running', .4, .4)
            assert receiver.position.x > .1, 'The moving collider did not push its dynamic neighbor'
            frozen_position, frozen_time = tuple(body.position), scenes.fixed_time
            scenes.time_scale = 0
            advance(10, 'frozen simulation', .4, .6)
            assert tuple(body.position) == frozen_position and scenes.fixed_time == frozen_time
            scenes.time_scale = 1
            advance(10, 'resumed', .6, .8)
            advance(25, 'completed', 1.1, 1.3)
            assert sorted(completions) == ['0', '1', 'body'], completions
            advance(20, 'settled kinematic target', 1.5, 1.7)
            assert receiver.position.x > 2.5
            api.use_smooth_delta_time, api.max_smooth_unscaled_time = True, .01
            smooth_values = [0., 0.]
            for index, independent in enumerate((False, True)):
                api.to(lambda i=index: smooth_values[i],
                       lambda value, i=index: smooth_values.__setitem__(i, value), 1., 1.) \
                    .set_ease(api.Ease.LINEAR).set_update(api.UpdateType.NORMAL, independent)
            engine.tick(.1)
            assert abs(smooth_values[0] - inx.Time.smooth_delta_time) < 2e-7
            assert .02 < smooth_values[0] < .1
            assert abs(smooth_values[1] - .01) < 2e-7
            observations.append(dict(stage='smoothed automatic clocks', values=list(smooth_values),
                                     smooth_delta=inx.Time.smooth_delta_time,
                                     raw_delta=inx.Time.unscaled_delta_time))
            linked = api.twn_move(body, Vector3(4, 0, 0), 2).set_link(obj)
            killed = []
            linked.on_kill(lambda: killed.append(True))
            scene.destroy_game_object(obj)
            engine.tick(.02)
            assert not linked.is_active() and killed == [True]
            packages.uninstall('infernux/tween')
            assert not any(_update_snapshot().values()), 'Plugin unload left frame callbacks registered'
        finally:
            scenes.stop()
            if packages is not None:
                packages.shutdown()
            engine.exit()
    args.proof.write_text(json.dumps(dict(passed=True, scope='installed package on real headless native frames',
                                         observations=observations), indent=2) + '\n', encoding='utf8')
    print('PASS installed-package clocks, paused fixed steps, contact pushing, settling and owner cleanup')


if __name__ == '__main__':
    main()
