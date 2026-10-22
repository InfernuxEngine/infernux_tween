"""Exercise the packed plugin through the public SDK in a fresh interpreter."""

import os
from pathlib import Path
import subprocess
import sys


def test_package_installs_imports_and_unloads_without_project_assets(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    code = r'''
import importlib, os, sys
from pathlib import Path
from infernux.engine.project_context import set_project_root
from infernux.plugins import InxPackage, PluginManager
from infernux.runtime_services import _update_snapshot

repository, root = map(Path, sys.argv[1:])
(root / "Assets").mkdir()
(root / "ProjectSettings").mkdir()
os.environ["INFERNUX_PACKAGE_CACHE_ROOT"] = str(root / "Cache/PackageLibrary")
set_project_root(str(root))
preview = InxPackage.export_source(str(repository), str(root / "plugin.inxpkg"), profile="release")
assert all(record["role"] in {"runtime", "control", "editor"} for record in preview.file_records)
manager = PluginManager(str(root), runtime=True)
try:
    state = manager.install_package(preview.package_path, install_dependencies=False)
    assert state.loaded and not state.error, state.error
    library = importlib.import_module("infernux_tween")
    assert Path(library.__file__).is_relative_to(root / "Packages")
    assert not list((root / "Assets").rglob("*"))
    assert not any(_update_snapshot().values())
    manager.uninstall(preview.metadata["reference"])
    assert "infernux_tween" not in sys.modules
    assert not any(_update_snapshot().values())
finally:
    manager.shutdown()
    set_project_root(None)
'''
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", code, str(repository), str(tmp_path)],
                            capture_output=True, text=True, env=environment, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
