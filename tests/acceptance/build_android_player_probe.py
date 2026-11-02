"""Cook the shared Tween fixture and validate it on one connected Android device."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from build_player_probe import authored_project, verify_player_image


GAME_NAME = 'InfernuxTweenAndroidProbe'


def stage_platform(args):
    source = args.engine / 'external/plugins/infernux_android/package/editor/infernux_android'
    destination = args.platform / 'infernux_android'
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('player', '__pycache__', '*.pyc'))
    player = destination / 'player'
    manifest = json.loads((args.native / 'android-player-Release.json').read_text())
    assert manifest['abi'] == 'arm64-v8a' and manifest['configuration'] == 'Release'
    libraries = player / 'arm64-v8a/jniLibs'
    libraries.mkdir(parents=True)
    reply = args.native / '.cmake/api/v1/reply'
    index = json.loads(sorted(reply.glob('index-*.json'))[-1].read_text())
    model = json.loads((reply / index['reply']['codemodel-v2']['jsonFile']).read_text())
    configuration, = model['configurations']
    assert configuration['name'] == 'Release'
    candidates = {}
    for target in configuration['targets']:
        metadata = json.loads((reply / target['jsonFile']).read_text())
        for artifact in metadata.get('artifacts', ()):
            path = args.native / artifact['path']
            candidates.setdefault(path.name, []).append(path)
    strip = next(line.split('=', 1)[1] for line in (args.native / 'CMakeCache.txt').read_text().splitlines()
        if line.startswith('CMAKE_STRIP:FILEPATH='))
    for name in manifest['native_libraries']:
        paths = candidates[name]
        assert len(paths) == 1, (name, paths)
        subprocess.run([strip, '--strip-debug', '-o', str(libraries / name), str(paths[0])], check=True)
    (libraries.parent / 'Player.inxmanifest').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copytree(args.engine / 'external/sdl_for_infernux/android-project/app/src/main/java', player / 'java')


def cook(args):
    from infernux.engine.build import (
        BuildConfiguration, BuildExporterRegistry, BuildProfile, BuildRequest, BuildService,
    )

    stage_platform(args)
    sys.path.insert(0, str(args.platform))
    from infernux_android.exporter import AndroidPlatformExporter, _android_application_id

    args.application_id = _android_application_id(args.game_name)
    args.probe_run_id = uuid4().hex
    script = (Path(__file__).parent / 'player/Bootstrap.py').read_text(encoding='utf8')
    marker = 'proof = dict(passed=passed,'
    assert script.count(marker) == 1
    script = script.replace(marker, f'proof = dict(probe_run_id={args.probe_run_id!r}, passed=passed,', 1)
    publish = "        destination.write_text(json.dumps(proof, indent=2) + '\\n', encoding='utf8')"
    assert script.count(publish) == 1
    script = script.replace(publish,
        "        temporary = destination.with_suffix('.tmp')\n"
        "        temporary.write_text(json.dumps(proof, indent=2) + '\\n', encoding='utf8')\n"
        "        temporary.replace(destination)", 1)
    bootstrap = args.proof.with_suffix('.android-bootstrap.py')
    bootstrap.write_text(script, encoding='utf8')

    registry = BuildExporterRegistry()
    registry.register('tween-player-acceptance', AndroidPlatformExporter())
    with authored_project(args, bootstrap_source=bootstrap) as catalog:
        settings = json.loads((args.project / 'ProjectSettings/BuildSettings.json').read_text())
        settings['game_name'] = args.game_name
        request = BuildRequest(str(args.project), 'android-arm64', str(args.output),
            profile=BuildProfile(configuration=BuildConfiguration.DEVELOPMENT, options={
                'android_artifact': 'apk', 'android_orientation': 'landscape',
                'window_width': 640, 'window_height': 360,
                'android_python_prefix': str(args.python_prefix),
                'build_cache_root': str(args.output.parent / (args.output.name + '-cache')),
                'build_settings': settings,
            }),
            asset_catalog_entries=tuple(catalog['entries']),
            runtime_type_records=tuple(catalog['runtime_type_records']),
            progress=lambda event: print(event.phase, event.message, flush=True))
        result = BuildService(registry).execute(request)
    summary = {'success': result.success, 'logs': list(result.logs),
        'application_id': args.application_id, 'game_name': args.game_name, 'probe_run_id': args.probe_run_id,
        'diagnostics': [{'code': item.code, 'message': item.message} for item in result.diagnostics],
        'artifacts': [{'path': item.path, 'kind': item.kind} for item in result.artifacts]}
    args.proof.with_suffix('.build.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert result.success, summary
    return next(Path(item.path) for item in result.artifacts if item.path.endswith('.apk'))


def run_player(args, apk):
    spec = importlib.util.spec_from_file_location('_tween_android_smoke',
        args.engine / 'tests/acceptance/android_player_smoke.py')
    smoke = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = smoke
    spec.loader.exec_module(smoke)
    adb = smoke.Adb(args.adb, args.serial)
    application_id = args.application_id
    smoke.install_apk(adb, apk, approve_oem_prompt=args.approve_oem_prompt)

    def read(path):
        return subprocess.run(adb.command('exec-out', 'run-as', application_id, 'cat', path),
            check=True, capture_output=True, timeout=30).stdout

    def proof_paths():
        found = adb.run('shell', 'run-as', application_id, 'find', 'files',
            '-name', 'tween-player-proof.json', check=False)
        return [line.strip() for line in found.splitlines() if line.strip().endswith('/tween-player-proof.json')]

    adb.run('shell', 'am', 'force-stop', application_id)
    if args.preserve_app_data:
        # Remove only this APK's own earlier probe result, never application data.
        for path in proof_paths():
            previous = json.loads(read(path))
            if previous.get('probe_run_id') == args.probe_run_id:
                adb.run('shell', 'run-as', application_id, 'rm', path)
    else:
        adb.run('shell', 'pm', 'clear', application_id)
    adb.run('shell', 'am', 'start', '-n', application_id + '/com.infernux.bootstrap.InfernuxActivity')
    deadline, pid, relative_proof = time.monotonic() + 120, '', ''
    while time.monotonic() < deadline:
        if not pid:
            pid = adb.run('shell', 'pidof', application_id, check=False).strip()
        paths = [path for path in proof_paths() if json.loads(read(path)).get('probe_run_id') == args.probe_run_id]
        if paths:
            relative_proof, = paths
            break
        time.sleep(.25)
    log = adb.run('logcat', '-d', '--pid=' + pid) if pid else 'Player PID was not observed.'
    args.proof.with_suffix('.player.log').write_text(log, encoding='utf8')
    assert relative_proof, 'Player produced no proof; see the captured application log'
    proof = json.loads(read(relative_proof))
    args.proof.write_text(json.dumps(proof, indent=2) + '\n')
    assert proof['passed'] and proof['player'], proof
    assert 'Packages/infernux/tween' in proof['library_origin'].replace('\\', '/')
    image = args.proof.with_suffix('.png')
    image.write_bytes(read(str(Path(relative_proof).with_name('tween-player.png')).replace('\\', '/')))
    verify_player_image(proof, image)
    proof.update(apk=str(apk), serial=args.serial, application_id=application_id,
        preserved_app_data=args.preserve_app_data,
        screenshot=str(image), player_log=str(args.proof.with_suffix('.player.log')),
        native_configuration='Release', apk_configuration='development')
    args.proof.write_text(json.dumps(proof, indent=2) + '\n')
    print('PASS Android Player: installed plugin, native computations, physics, lifecycle and rendered UI')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('engine', 'fixture', 'package', 'project', 'platform', 'native', 'python-prefix', 'output', 'proof', 'adb'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--game-name', default=GAME_NAME)
    parser.add_argument('--preserve-app-data', action='store_true')
    parser.add_argument('--approve-oem-prompt', action='store_true')
    parser.add_argument('--cook-only', action='store_true')
    parser.add_argument('--run-only', action='store_true')
    args = parser.parse_args()
    for name in ('engine', 'fixture', 'package', 'project', 'platform', 'native', 'python_prefix', 'output', 'proof', 'adb'):
        setattr(args, name, getattr(args, name).resolve())
    args.proof.parent.mkdir(parents=True, exist_ok=True)
    if args.run_only:
        previous = json.loads(args.proof.with_suffix('.build.json').read_text())
        args.application_id, args.probe_run_id = previous['application_id'], previous['probe_run_id']
        apk = next(Path(item['path']) for item in previous['artifacts'] if item['path'].endswith('.apk'))
    else:
        apk = cook(args)
    if not args.cook_only:
        run_player(args, apk)


if __name__ == '__main__':
    main()
