"""Cook the shared Tween fixture and verify gameplay and pixels in a WebGPU browser."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import sys
from threading import Thread

from build_player_probe import authored_project, verify_player_image


WEB_ADAPTER = '''

class PlatformFixtureBootstrap(_TweenRuntimeProbe):
    def start(self):
        self._browser_capture_frames = 0
        super().start()

    def _capture_output(self):
        self._browser_capture_frames += 1
        if self._browser_capture_frames >= 3:
            self._observations.append({'stage': 'browser_capture_pending'})
            self._complete_checks()

    def _request_exit(self, code):
        # The browser controller captures the canvas before closing the page.
        pass
'''


def cook(args):
    from infernux.engine.build import (
        BuildConfiguration, BuildExporterRegistry, BuildProfile, BuildRequest, BuildService,
    )

    source = args.engine / 'external/plugins/infernux_web/package/editor/infernux_web'
    destination = args.platform / 'infernux_web'
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('player', '__pycache__', '*.pyc'))
    shutil.copytree(args.runtime, destination / 'player')
    sys.path.insert(0, str(args.platform))
    from infernux_web.exporter import WebPlatformExporter

    script = (Path(__file__).parent / 'player/Bootstrap.py').read_text(encoding='utf8')
    script = script.replace('class PlatformFixtureBootstrap(inx.InxComponent):',
        'class _TweenRuntimeProbe(inx.InxComponent):', 1) + WEB_ADAPTER
    bootstrap = args.proof.with_suffix('.bootstrap.py')
    bootstrap.write_text(script, encoding='utf8')
    registry = BuildExporterRegistry()
    registry.register('tween-player-acceptance', WebPlatformExporter())
    with authored_project(args, bootstrap_source=bootstrap) as catalog:
        settings = json.loads((args.project / 'ProjectSettings/BuildSettings.json').read_text())
        settings['game_name'] = 'InfernuxTweenWebProbe'
        request = BuildRequest(str(args.project), 'web-wasm32', str(args.output),
            profile=BuildProfile(configuration=BuildConfiguration.DEVELOPMENT, options={
                'display_mode': 'windowed', 'window_width': 640, 'window_height': 360,
                'build_cache_root': str(args.output.parent / (args.output.name + '-cache')),
                'build_settings': settings,
            }),
            asset_catalog_entries=tuple(catalog['entries']),
            runtime_type_records=tuple(catalog['runtime_type_records']),
            progress=lambda event: print(event.phase, event.message, flush=True))
        result = BuildService(registry).execute(request)
    summary = {'success': result.success, 'logs': list(result.logs),
        'diagnostics': [{'code': item.code, 'message': item.message} for item in result.diagnostics],
        'artifacts': [{'path': item.path, 'kind': item.kind} for item in result.artifacts]}
    args.proof.with_suffix('.build.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert result.success, summary


def run_player(args):
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(('127.0.0.1', 0),
        partial(SimpleHTTPRequestHandler, directory=str(args.output)))
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    console, errors = [], []

    def record_console(message):
        line = message.type + ': ' + message.text
        console.append(line)
        print(line, flush=True)

    def record_error(error):
        errors.append(str(error))
        print('pageerror: ' + str(error), flush=True)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True,
                args=['--enable-unsafe-webgpu', '--ignore-gpu-blocklist'])
            try:
                page = browser.new_page(viewport={'width': 640, 'height': 360}, device_scale_factor=1)
                page.on('console', record_console)
                page.on('pageerror', record_error)
                page.goto(f'http://127.0.0.1:{server.server_port}/infernux-player.html',
                    wait_until='domcontentloaded')
                page.wait_for_function('''() => document.querySelector('#canvas').dataset.infernuxState === 'aborted' ||
                    (typeof Module !== 'undefined' && Module.FS &&
                    Module.FS.analyzePath('/infernux-player-data/tween-player-proof.json').exists)''',
                    timeout=180000)
                assert page.locator('#canvas').get_attribute('data-infernux-state') != 'aborted', console
                proof = json.loads(page.evaluate('''() => Module.FS.readFile(
                    '/infernux-player-data/tween-player-proof.json', {encoding:'utf8'})'''))
                args.proof.write_text(json.dumps(proof, indent=2) + '\n')
                assert proof['passed'] and proof['player'], proof
                assert proof['native_origin'] == 'built-in', proof['native_origin']
                assert 'Packages/infernux/tween' in proof['library_origin']
                page.wait_for_selector('#canvas[data-infernux-state="ready"]', timeout=30000)
                page.wait_for_selector('#infernux-loader', state='detached', timeout=30000)
                page.evaluate('''() => new Promise(resolve => requestAnimationFrame(
                    () => requestAnimationFrame(resolve)))''')
                image = args.proof.with_suffix('.png')
                page.locator('#canvas').screenshot(path=str(image))
                verify_player_image(proof, image)
                assert not errors, errors
                proof['observations'].append({'stage': 'rendered', 'capture': 'browser-canvas'})
                proof.update(screenshot=str(image), player_log=str(args.proof.with_suffix('.browser.log')),
                    browser_version=browser.version, javascript_errors=errors)
                args.proof.write_text(json.dumps(proof, indent=2) + '\n')
            except Exception:
                diagnostics = page.evaluate('''() => ({
                    state: document.querySelector('#canvas')?.dataset.infernuxState,
                    diagnostics: document.querySelector('#canvas')?.dataset.infernuxDiagnostics,
                    status: document.querySelector('#status')?.textContent,
                    filesystem: typeof Module !== 'undefined' && !!Module.FS
                })''')
                args.proof.with_suffix('.failure.json').write_text(json.dumps(diagnostics, indent=2) + '\n')
                page.screenshot(path=str(args.proof.with_suffix('.failure.png')))
                raise
            finally:
                browser.close()
    finally:
        server.shutdown()
        serving.join()
        server.server_close()
        args.proof.with_suffix('.browser.log').write_text('\n'.join(console + errors) + '\n', encoding='utf8')
    print('PASS Web Player: installed plugin, native computations, physics, lifecycle and rendered UI')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('engine', 'fixture', 'package', 'project', 'platform', 'runtime', 'output', 'proof'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--browser', type=Path)
    parser.add_argument('--cook-only', action='store_true')
    parser.add_argument('--run-only', action='store_true')
    args = parser.parse_args()
    for name in ('engine', 'fixture', 'package', 'project', 'platform', 'runtime', 'output', 'proof'):
        setattr(args, name, getattr(args, name).resolve())
    args.proof.parent.mkdir(parents=True, exist_ok=True)
    if not args.run_only:
        cook(args)
    if not args.cook_only:
        assert args.browser is not None, '--browser is required when running the Player'
        run_player(args)


if __name__ == '__main__':
    main()
