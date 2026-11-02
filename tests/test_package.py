"""Exercise the packed plugin through the public SDK in a fresh interpreter."""

import os
from pathlib import Path
import subprocess
import shutil
import sys
import infernux
import pytest


@pytest.mark.parametrize("runtime", [True, False], ids=["player", "editor"])
def test_package_installs_imports_and_unloads_without_project_assets(tmp_path, runtime):
    source = Path(__file__).resolve().parents[1]
    repository = tmp_path / "author-repository"
    shutil.copytree(source / "package", repository / "package")
    # If a build file leaked into the archive or ran at install, this fixture
    # would either appear in the installed tree or abort the installation.
    (repository / "CMakeLists.txt").write_text('message(FATAL_ERROR "author build must never run on install")\n', encoding="utf-8")
    for name in ("native/CMakeLists.txt", "native/kernel.cpp", "build/compiler-cache", ".github/workflows/native.yml"):
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("outer author-only sentinel\n", encoding="utf-8")
    installation = tmp_path / "consumer-project"
    installation.mkdir()
    code = r'''
import importlib, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from infernux.engine.project_context import set_project_root
from infernux.plugins import InxPackage, PluginManager
from infernux.runtime_services import _update_snapshot
from infernux.core.data_asset import get_registered_data_asset_types

repository, root = map(Path, sys.argv[1:3])
(root / "Assets").mkdir()
(root / "ProjectSettings").mkdir()
os.environ["INFERNUX_PACKAGE_CACHE_ROOT"] = str(root / "Cache/PackageLibrary")
set_project_root(str(root))
preview = InxPackage.export_source(str(repository), str(root / "plugin.inxpkg"), profile="release")
assert all(record["role"] in {"runtime", "control", "editor"} for record in preview.file_records)
entries = InxPackage.inspect(preview.package_path).logical_entries
assert not any("CMakeLists.txt" in path or path.startswith(("native/", "build/", ".github/")) for path in entries)
runtime = sys.argv[4] == "player"
manager = PluginManager(str(root), runtime=runtime)
try:
    state = manager.install_package(preview.package_path, install_dependencies=False)
    assert state.loaded and not state.error, state.error
    library = importlib.import_module("infernux_tween")
    assert ("infernux.tween.settings", library.TweenSettings) in get_registered_data_asset_types()
    assert Path(library.__file__).is_relative_to(root / "Packages")
    assert not list((root / "Assets").rglob("*"))
    assert not list((root / "Packages").rglob("CMakeLists.txt"))
    assert not list((root / "Packages").rglob("kernel.cpp"))
    assert not list((root / "Packages").rglob("compiler-cache"))
    assert not any(_update_snapshot().values())
    if not runtime:
        from infernux.engine.interaction.handles import EditorHandleRegistry
        from infernux.engine.ui.inspector_components import _PY_COMPONENT_RENDERERS
        assert any(p.provider_id == "infernux.tween.paths" for p in EditorHandleRegistry.instance().providers)
        assert callable(_PY_COMPONENT_RENDERERS["TweenPath"])
        library.TweenEditorPreview.start()
        assert len(_update_snapshot()["editor_update"]) == 1
    manager.uninstall(preview.metadata["reference"])
    assert "infernux_tween" not in sys.modules
    assert not any(identity == "infernux.tween.settings" for identity, _ in get_registered_data_asset_types())
    if not runtime:
        assert not any(p.provider_id == "infernux.tween.paths" for p in EditorHandleRegistry.instance().providers)
        assert _PY_COMPONENT_RENDERERS.get("TweenPath") is None
    assert not any(_update_snapshot().values())
finally:
    manager.shutdown()
    set_project_root(None)
'''
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    sdk_root = str(Path(infernux.__file__).resolve().parent.parent)
    result = subprocess.run([sys.executable, "-c", code, str(repository), str(installation), sdk_root, "player" if runtime else "editor"],
                            capture_output=True, text=True, env=environment, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
