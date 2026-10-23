# Tween

需要 Infernux **0.4.3 热修 4 或更新版本**。

```python
import infernux_tween as tween
from infernux import Vector2, Vector3

move = tween.do_local_move(transform, Vector3(80, 20, 0), 0.4)
move.set_ease(tween.Ease.IN_OUT_SINE)
tween.sequence().append(move).append_interval(0.1).append_callback(on_finished)
tween.do_size_delta(image, Vector2(240, 80), 0.3)
```

函数采用 snake_case，类采用 PascalCase，枚举成员采用 UPPER_SNAKE_CASE。原生目标作为第一个参数；枚举仍传枚举，字符串端点仍传字符串。颜色使用引擎的 RGBA 列表，不添加另一套包装类型。

`to`、`to_axis`、`to_alpha`、`to_array` 创建有类型的补间。`set_ease` 接受 Ease、原生 AnimationCurve、EaseCurve 或四参数函数 `(time, duration, overshoot_or_amplitude, period)`。`set_options` 根据浮点、向量、颜色、旋转或字符串类型表达不同选项。`set_as` 复制 Tween/TweenParams 的通用设置，不复制目标或类型专用选项。

`from_(is_relative)` 的一个布尔值表示相对；`from_(set_immediately, is_relative)` 的两个布尔值分别表示立即写入、相对。不指定起点且需要延后捕获时，写 `from_(set_immediately=False, is_relative=False)`。指定值的 `from_(value, set_immediately=False, is_relative=True)` 在调用时固定端点，只延迟写入。`change_start_value`、`change_end_value`、`change_values` 的时长参数为 `new_duration`；`goto(seconds)` 不包含开始延时。

在开始播放或插入序列前配置。序列支持嵌套、插入/前置/并行回调、间隔和增量循环。回调里的暂停、跳转、销毁会终止当前调度。实例控制一个补间；模块筛选控制必须传目标或 ID；`*_all` 明确操作全部。`set_link` 关联 GameObject 生命周期，暂停的补间也会清理。

快捷操作覆盖 Transform、Rigidbody、材质、UI、精灵/线条、相机、光照和音频。刚体通过 Fixed 和 move_position/move_rotation 移动。Graphic 淡出修改颜色 alpha，UIGroup 修改 alpha，AudioSource 修改音量。材质命名属性的参数放在 duration 前。路径有局部/世界坐标、朝向、路点回调、跳转与 Gizmo。Jump/Punch/Shake/Spiral 和混合动画复用同一时钟。引擎尚无的材质 UV 变换、文本描边发光、整体 UI Transform 缩放等不会用无效字段冒充；详细边界见仓库 README。

添加「Tween Animation」「Tween Path」「Tween Visual Manager」即可使用原生 Inspector 字段与场景路径手柄。打开「动画 / Tween」进行可恢复预览，保存、撤销、切换选择和进入 Play 都会还原创作值。持久事件使用原生列表、引用与 Undo，精确关联组件实例；不可表达的参数类型不会被伪装成字符串。预览不发送游戏回调。

```python
characters = tween.TextTweenAnimator(label)
characters.do_offset_char(0, Vector3(0, 12, 4), 0.4).from_()
characters.range().do_fade(0, 0.4).from_()
```

索引采用原生字素，位移、Euler 角和缩放是真正的 Vector3，正 Y 与 Transform 一样向上。逐角偏移保留 XYZ；区间倾斜包含终点。这些操作占用 Manual 层，与 Text Animator 的 Effects、Appearance 层按顺序组合。布局变化会终止旧索引动画；一轮管理器更新只提交一次共享缓冲。`reset`、`dispose` 还原这一层。

插件自行管理更新注册，空组或全部暂停时没有活动更新。Manual 补间只由 `manual_update(scaled_delta, unscaled_delta)` 驱动，独立时钟采用不受缩放的时间。`get_time_scale`、`set_time_scale` 控制默认管理器。Spring 是独立的有状态弹簧辅助类，在自己的模拟时钟中调用 pull、animate 和 update。
