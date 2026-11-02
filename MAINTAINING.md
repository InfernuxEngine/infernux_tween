# Development

Use Python 3.13 and Infernux 0.4.8 or newer from the current engine checkout or its published package. Engine and plugin are developed together.

```powershell
python -m pip install -r sdk-requirements.txt
python examples/quick_start.py
python package.py
```

For installation coverage, run `python -m pytest tests/test_package.py`. Run the functional tests relevant to changed behavior. The quick start uses native scene transforms and engine curves, then demonstrates sequences, paths, callbacks and ordinary Python numerical values. Its `--package` option exercises the exported plugin.

The editor components live directly under `package/runtime/`; the scripting API is in `package/runtime/infernux_tween/`; editor tools are in `package/editor/`. Only `package/` enters the plugin archive.

Keep scene control, callbacks and authoring in Python. Engine C++ owns numerical recipes, curve sampling and bulk work. Pure numerical batches can release the GIL; calling Python or mutating a Python target requires it. Prepare reusable data at configuration or startup rather than validating it repeatedly in each sample.

Share the engine's AnimationCurve assets and native snapshots. Retain scene ownership and callback ordering. Keep source organization direct, and avoid parallel APIs, compatibility layers and automatic recovery paths for old SDKs.

## Release

Build the SDK and plugin from the intended current sources, run the quick start and relevant functional checks, then export the plugin. The release tag identifies the version in `package/inx_package.json`. Publish the plugin through its normal release flow. The engine owns the native build and release; the plugin requires engine 0.4.8 or newer.

The GitHub workflow accepts `sdk_package` for a current SDK wheel URL; `INFERNUX_SDK_PACKAGE` supplies the repository default. Without either, it installs the current package from the package index. The repository does not pin older platform-specific SDK URLs.

When a plugin update needs new native engine APIs, verify it against the matching
engine build through `sdk_package`, then publish the plugin asset before publishing
the engine catalog that advertises it. The engine's catalog generator reads
`packaging/official_plugin_releases.json`; its Tween entry, generated registry and
plugin manifest must agree on version 0.3.1 and minimum engine 0.4.8.

Existing local numerical corpora and provenance remain private development material. First-stage development does not add more comparison samplers, hash archives or platform matrices. Further numerical edge cases and performance experiments follow the functional delivery.
