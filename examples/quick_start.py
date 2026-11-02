"""Run curve, scene motion, sequences, paths and scalar tweens with an Infernux SDK."""
import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def run_demo():
    from infernux import AnimationCurve, Vector3
    from infernux.lib import SceneManager
    import infernux_tween as tween

    scenes = SceneManager.instance()
    scene = scenes.create_scene("补间功能演示")
    tween.clear(True)
    try:
        settings = tween.TweenSettings(default_ease_type=tween.Ease.LINEAR)
        settings.apply()
        player = scene.create_game_object("演示物体")
        follower = scene.create_game_object("路径物体")
        curve = AnimationCurve.ease_in_out(0., 0., 1., 1.)
        events, samples = [], []
        values = {"整数": 0, "浮点": 0.0}

        move = tween.twn_move(player.transform, Vector3(2, 1, 0), 1.).set_ease(curve)
        scale = tween.twn_scale(player.transform, 1.5, 1.).set_ease(tween.Ease.IN_OUT_SINE)
        timeline = tween.sequence().set_update(tween.UpdateType.MANUAL)
        timeline.append(move).join(scale).set_loops(2, tween.LoopType.YOYO)
        timeline.on_complete(lambda: events.append("往返序列完成"))
        completion = timeline.wait_for_completion(return_custom_yield_instruction=True)

        path = tween.twn_path(follower.transform,
            [Vector3(0, 0, 0), Vector3(.5, 1, 0), Vector3(2, 0, 0)], 1.)
        path.set_ease(tween.Ease.LINEAR).set_update(tween.UpdateType.MANUAL)
        path.on_complete(lambda: events.append("路径完成"))

        tween.to(lambda: values["整数"], lambda value: values.__setitem__("整数", value),
                 10, 1.).set_update(tween.UpdateType.MANUAL)
        tween.to(lambda: values["浮点"], lambda value: values.__setitem__("浮点", value),
                 1.0, 1.).set_update(tween.UpdateType.MANUAL)

        for frame in range(1, 129):
            tween.manual_update(1 / 64, 1 / 64)
            if frame in (32, 64, 96, 128):
                samples.append({"时间": frame / 64, "位置": list(player.transform.position),
                                "缩放": list(player.transform.local_scale)})
        return {"场景": scene.name, "设置资产类型": type(settings).__name__,
                "序列等待已结束": not completion.keep_waiting,
                "曲线中点": curve.evaluate(.5), "运动采样": samples,
                "路径终点": list(follower.transform.position), "数值": values,
                "数值类型": {name: type(value).__name__ for name, value in values.items()}, "事件": events}
    finally:
        tween.clear(True)
        scenes.unload_scene(scene)


def run_package(package, project):
    from infernux.engine.project_context import set_project_root
    from infernux.plugins import PluginManager
    project = project.resolve()
    (project / "Assets").mkdir(parents=True, exist_ok=True)
    (project / "ProjectSettings").mkdir(exist_ok=True)
    os.environ["INFERNUX_PACKAGE_CACHE_ROOT"] = str(project / "Cache/PackageLibrary")
    set_project_root(str(project))
    packages = PluginManager(str(project), runtime=True)
    try:
        packages.install_package(str(package.resolve()), install_dependencies=False)
        return run_demo()
    finally:
        packages.shutdown()
        set_project_root(None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, help="Install and run a built .inxpkg instead of repository sources")
    parser.add_argument("--project", type=Path, help="Keep a demonstration project instead of using a temporary one")
    args = parser.parse_args()
    if args.package:
        with TemporaryDirectory(prefix="infernux-tween-") as folder:
            result = run_package(args.package, args.project or Path(folder))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "package/runtime"))
        result = run_demo()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
