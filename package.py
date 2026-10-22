"""Build with the published Infernux SDK; no engine checkout is required."""

import argparse
import json
from pathlib import Path

from infernux.plugins.cli import main as package_cli
from infernux.plugins.package import InxPackage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "package/inx_package.json").read_text(encoding="utf-8"))
    if args.tag and args.tag != "v" + manifest["version"]:
        raise ValueError("Release tag must match the package manifest version")
    artifact = manifest["reference"].replace("/", ".") + ".inxpkg"
    destination = root / "out" / artifact
    preview = InxPackage.export_source(str(root), str(destination), profile="release")
    inspected = InxPackage.inspect(str(destination))
    if inspected.metadata != preview.metadata:
        raise RuntimeError("Packed metadata differs from the authored package")
    if any(path.startswith(("tests/", "examples/", ".github/")) for path in inspected.logical_entries):
        raise RuntimeError("Development files must stay outside the plugin")
    result = package_cli(["package", "release-manifest", str(destination),
                          "--output", str(root / "out/infernux-plugin-release.json"),
                          "--tag", "v" + manifest["version"]])
    if result:
        raise RuntimeError("Release metadata generation failed")
    entry = {key: inspected.metadata[key] for key in
             ("reference", "name", "version", "intro", "intros", "engine", "pages")}
    entry.update(artifact=artifact, dependencies=[], category="animation", targets=[],
                 repository="https://github.com/InfernuxEngine/infernux_tween",
                 source={"type": "url", "location":
                         f"https://downloads.infernux-engine.com/plugins/{manifest['reference'].replace('/', '.')}/{manifest['version']}/{artifact}"})
    (root / "out/official-registry-entry.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{artifact}: {destination.stat().st_size} bytes; {len(inspected.logical_entries)} files")


if __name__ == "__main__":
    main()
