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

`From(value, set_immediately=False, relative=True)` 在调用时固定显式端点，等播放时
才写入目标；没有指定起点的 `From(set_immediately=False)` 则在播放开始时捕获目标。
字符串和四元数的相对规则见仓库 README。普通属性补间可以用 `ChangeStartValue`、
`ChangeEndValue`、`ChangeValues` 修改端点并回到动画起点，保留已经消耗的延时和
播放／暂停状态。传入新的正时长才替换时长；速度模式下该参数为新速度。
`ChangeEndValue(value, True)` 捕获当前值作为新起点并保留时长。序列子项忽略这些
调用；倒放动画回到起点后停止。

`Goto(seconds)` 使用不含首次延时的动画时间。Sequence 的 `SetDelay(seconds)`
默认在开头加入随循环重复的间隔；传入 `as_prepended_interval_if_sequence=False`
则只在首次播放前等待。序列回调内暂停会保留该回调所在的位置，`Play()` 从那里继续，
包括并行和嵌套子动画。根动画播放期间可用 `SetUpdate` 切换时钟；子动画跟随根时钟。

使用 `ShortcutExtensions.DOLocalMove(transform, (80, 20, 0), 0.4)`、
`DOScale`、`DORotate`、`DOColor`、`DOFade`、`DOSize`、`DOValue` 等快捷方法，
目标使用引擎现有 Transform、UI、材质、灯光、相机或音频组件。Python 接口
显式传入目标，不给原生类型动态添加方法。运动学刚体移动通过 Fixed 阶段的
`move_position` 执行，刚体旋转通过 `move_rotation` 执行。四元数使用最短弧插值，
欧拉角支持超过一周的旋转。

快捷方法自动设置 target；`DOTween.Pause(target)`、`Restart(target)`、
`Kill(target)` 可统一控制目标，也可先 `SetId("menu")` 后按 ID 控制。
Sequence 支持整组缓动、相对值和 Restart/Yoyo 循环；Incremental 仅用于 Tweener。

自定义缓动使用原生 `AnimationCurve`，持续字效之外的 CPU 曲线可用 `EaseCurve`。
Jump、Punch、Shake、Spiral 可跳转采样；Blendable 位移、缩放、旋转和颜色只叠加自身
的变化，不覆盖其它动画。作者组件会将运行时动画关联到目标，目标销毁时清理暂停中的动画。

字符串补间按引擎字素推进，组合重音和连接的 emoji 不会被从中间切开。
`ShortcutExtensions.DOText(label, "欢迎回来 世界", 0.8)` 可以逐步显示文字，
原生颜色、字号和换行标签保持完整；计数器、字号和可见数分别使用
`DOCounter`、`DOFontSize`、`DOMaxVisibleCharacters`。

已有文字可以按字符批量做几何动画：

```python
from infernux_tween import DOTween, DOTweenTextAnimator

characters = DOTweenTextAnimator(label)
sequence = DOTween.Sequence()
sequence.Join(characters.Range().DOOffset((0, 12), 0.4).From())
sequence.Join(characters.Range().DOFade(0, 0.4).From())
sequence.SetLink(label.game_object)
```

`Character`、`Range`、`Word`、`Line` 使用原生字素索引；偏移使用文字局部坐标，
Y 正方向向下，旋转单位为度。它使用 Manual 层，可与 Text Animator 的持续字效、
出入场叠加。同一文字使用一个 Manual 层控制器；`Reset` 或 `Dispose` 还原该层。
布局改变会终止旧索引动画，因此应在 `DOText` 完成文字修改后再创建字符动画。
