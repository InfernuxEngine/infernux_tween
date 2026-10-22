# Maintenance

This is an independent official plugin. The engine does not contain a submodule,
CMake dependency or bundled source copy of this repository.

Use CPython 3.13 and install `sdk-requirements.txt` in a development environment.
The SDK is pinned to the published Infernux 0.4.3 build 2 wheel on Windows/Linux.
Run `python -m pytest`, then `python package.py`. Only `package/` enters the
archive; tests and examples remain development content.

After product/platform validation, change `package/inx_package.json` once and
push its matching `v<version>` tag. CI tests both desktop platforms before
creating a GitHub Release containing the package, the engine release manifest,
and `official-registry-entry.json`.

The engine release maintainer reviews that entry, registers it in
`packaging/official_plugin_releases.json`, uploads the exact GitHub package to
R2 using `scripts/release/publish_plugin_objects.py --reference infernux/tween`,
and publishes the complete official registry last. Do not advertise a package
before its public asset and platform validation exist. Plugin releases do not
require a new engine wheel.
