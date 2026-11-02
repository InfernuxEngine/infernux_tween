"""Runtime identity and optional path drawing use the live scheduler."""
import json
from pathlib import Path
from types import SimpleNamespace

import infernux_tween as tween
from infernux_tween import TweenManager


def test_version_identifies_the_installed_plugin_manifest():
    manifest = Path(__file__).parents[1] / 'package/inx_package.json'
    assert tween.version == json.loads(manifest.read_text(encoding='utf8'))['version']


def test_instance_tracks_initialization_and_full_runtime_clear(monkeypatch):
    manager = TweenManager()
    monkeypatch.setattr(tween, '_default_manager', manager)
    assert 'instance' in dir(tween) and tween.instance is None
    manager.init()
    assert tween.instance is manager
    manager.clear()
    assert tween.instance is manager
    manager.clear(destroy=True)
    assert tween.instance is None
    handle = manager.to(lambda: 0., lambda value: None, 1., 1.)
    assert tween.instance is manager
    handle.kill()


def test_runtime_path_gizmo_switch_skips_geometry_and_preserves_editor_state(monkeypatch):
    from editor import TweenTools as tools

    manager = TweenManager()
    monkeypatch.setattr(tween, '_default_manager', manager)
    monkeypatch.setattr(tools, 'SceneManager', SimpleNamespace(instance=lambda: SimpleNamespace(is_playing=lambda: True)))
    calls = []
    monkeypatch.setattr(manager, '_matching', lambda: calls.append('geometry') or ())
    previous = tools.Gizmos.color
    tween.draw_gizmos = False
    tools._draw_paths(None)
    assert not calls and tools.Gizmos.color == previous
    tween.draw_gizmos = True
    tools._draw_paths(None)
    assert calls == ['geometry'] and tools.Gizmos.color == previous
