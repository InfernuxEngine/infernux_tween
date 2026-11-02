"""Install the archive and verify real Editor Play reporting and hook cleanup."""
import argparse
import importlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import infernux as inx
from infernux.debug import Debug
from infernux.engine.play_mode import PlayModeManager, PlayModeState
from infernux.lib import RuntimeMode, SceneManager
from infernux.plugins import PluginManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    observations = []
    with tempfile.TemporaryDirectory(prefix='infernux-tween-editor-') as folder:
        root = Path(folder)
        (root / 'Assets').mkdir()
        (root / 'ProjectSettings').mkdir()
        os.environ['INFERNUX_PACKAGE_CACHE_ROOT'] = str(root / 'Cache/PackageLibrary')
        engine = inx.Engine(mode=RuntimeMode.Headless)
        packages = None
        try:
            engine.init_headless(folder)
            play_mode = PlayModeManager.instance()
            original_listeners = tuple(play_mode._state_change_listeners)
            packages = PluginManager(folder, engine=engine, runtime=False)
            state = packages.install_package(str(args.package.resolve()), install_dependencies=False)
            assert state.loaded and not state.error, state.error
            api = importlib.import_module('infernux_tween')
            assert Path(api.__file__).is_relative_to(root / 'Packages')
            scenes = SceneManager.instance()
            scene = scenes.get_active_scene()
            assert scene is not None

            def settle(expected):
                for _ in range(24):
                    engine.tick(.02)
                    if play_mode.state == expected:
                        return
                raise AssertionError((expected, play_mode.state))

            for cycle in range(2):
                assert play_mode.enter_play_mode()
                settle(PlayModeState.PLAYING)
                assert api.get_editor_report() == {'peak_tweeners': 0, 'peak_sequences': 0, 'safe_mode_errors': 0}
                api.show_editor_report = True
                api.to(lambda: 0., lambda value: None, 1., 1.)
                api.sequence().append(api.to(lambda: 0., lambda value: None, 1., 1.))
                engine.tick(.02)
                with patch.object(Debug, 'log', wraps=Debug.log) as messages:
                    assert play_mode.exit_play_mode()
                    settle(PlayModeState.EDIT)
                reports = [str(call.args[0]) for call in messages.call_args_list
                           if call.args and str(call.args[0]).startswith('Tween Play report:')]
                assert reports == ['Tween Play report: peak roots 2 tweeners / 1 sequences; 0 handled errors'], reports
                observations.append(dict(cycle=cycle, reports=reports, counters=api.get_editor_report()))
                api.clear()
            packages.uninstall('infernux/tween')
            assert tuple(play_mode._state_change_listeners) == original_listeners
        finally:
            if packages is not None:
                packages.shutdown()
            engine.exit()
    args.proof.write_text(json.dumps(dict(passed=True, observations=observations), indent=2) + '\n', encoding='utf8')
    print('PASS installed Editor package: two real Play/Stop reports, next-session reset and listener cleanup')


if __name__ == '__main__':
    main()
