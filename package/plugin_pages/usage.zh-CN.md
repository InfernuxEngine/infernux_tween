# 动画补间

添加“Animation / Tween Animation”“Tween Path”或“Tween Visual Manager”，
可在 Inspector 中配置动画。目标物体为空时使用当前物体；材质通过标准资产选择框指定。
路径点使用引擎列表控件和 Scene 位置控制柄，拖动通过引擎事务服务记录撤销。
“动画 / 补间动画”面板支持预览、暂停、继续和停止还原；保存、撤销、切换选择和进入
Play 也会恢复原始值。预览不发送游戏事件。生命周期管理组件可显式设置启用、禁用时
的播放/暂停/重播等操作，适用于对象池。

路径使用 `ShortcutExtensions.DOPath(transform, points, seconds, PathType.CatmullRom)`，
支持直线、Catmull-Rom 和三次贝塞尔。匀速使用 `Ease.Linear`；`SetSpeedBased()`
将时长参数解释为每秒移动单位，`ForceInit()` 后可查询路径长度。四元数快捷方法使用最短弧旋转。

`SetLink(game_object)` 在物体销毁时清理动画，包括暂停的动画。对象池行为由
`LinkBehaviour` 选择；序列关联根节点。`WaitFor...` 复用引擎协程，异步版本需要调用方已有的 asyncio 循环。

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
