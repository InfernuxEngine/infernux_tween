# 动画补间

交互弹簧可使用 `Spring(1, stiffness=200, damping=10)`：交互时调用 `Pull(0.2)`，
在固定模拟步中调用 `Update(fixed_delta)`。重复拉动保留速度，`Animate(target)` 改变锚点，
`IsResting()` 可判断是否停止更新。弹簧有独立的动态状态，不混入可任意跳转的时间轴。

使用 `DOTween.To(getter, setter, end_value, duration)` 创建属性补间，使用
`DOTween.Sequence().Append(tween).Join(other_tween)` 编排序列。参数应在播放或
加入序列前配置；同一个子动画只能属于一个序列。时间单位为秒。

支持 `SetEase`、`SetDelay`、`SetLoops`、`SetUpdate`、`SetAutoKill` 链式配置；
通过 `Play`、`Pause`、`Restart`、`Rewind`、`Goto`、`Complete`、`Kill` 控制播放。
回调在引擎线程执行，手动更新与自动更新相互独立。

使用 `ShortcutExtensions.DOLocalMove(transform, (80, 20, 0), 0.4)`、
`DOScale`、`DORotate`、`DOColor`、`DOFade`、`DOSize`、`DOValue` 等快捷方法，
目标使用引擎现有 Transform、UI、材质、灯光、相机或音频组件。Python 接口
显式传入目标，不给原生类型动态添加方法。运动学刚体移动通过 Fixed 阶段的
`move_position` 执行。四元数旋转等其余适配仍待补齐。

快捷方法自动设置 target；`DOTween.Pause(target)`、`Restart(target)`、
`Kill(target)` 可统一控制目标，也可先 `SetId("menu")` 后按 ID 控制。
Sequence 支持整组缓动、相对值和 Restart/Yoyo 循环；Incremental 仅用于 Tweener。

当前为开发阶段的播放核心，尚未正式发布可视化组件与路径工具。
