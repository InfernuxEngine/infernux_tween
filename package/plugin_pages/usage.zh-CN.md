# 动画补间

使用 `DOTween.To(getter, setter, end_value, duration)` 创建属性补间，使用
`DOTween.Sequence().Append(tween).Join(other_tween)` 编排序列。参数应在播放或
加入序列前配置；同一个子动画只能属于一个序列。时间单位为秒。

支持 `SetEase`、`SetDelay`、`SetLoops`、`SetUpdate`、`SetAutoKill` 链式配置；
通过 `Play`、`Pause`、`Restart`、`Rewind`、`Goto`、`Complete`、`Kill` 控制播放。
回调在引擎线程执行，手动更新与自动更新相互独立。

当前为开发阶段的播放核心，尚未正式发布可视化组件与路径工具。
