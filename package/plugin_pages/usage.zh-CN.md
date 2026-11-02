# Tween

最低支持 Infernux 0.4.8。在引擎插件管理器中选择 Infernux Tween 并安装即可。
原生曲线和数值工具由引擎提供，插件安装时不编译额外的原生库。

## 循环播放状态

普通补间和序列通过原生的单循环进度、整数循环次数及独立延迟进度推进。
累计时间只用于查询和时间线遍历，不再作为不断增长的单精度帧累加器。
因此长期循环仍能按帧推进；`goto`、回退、重播和回调中的重新定位会同步更新播放状态。
时间配方可以共享，播放状态始终属于各自的补间实例。

首次 `on_start` 和 `on_play` 读取的是这一帧应用前的进度。在其中暂停或跳转不会取消
已经捕获的当前帧，删除补间则会取消。修改终点和时长会影响这一帧的应用结果；
之后的 `on_update` 读取应用后的进度。

`position` 返回当前循环的进度时间，`completed_loops()` 返回整数循环次数。
累计时间查询继续保持公开接口的单精度结果；长期循环时应使用前两者观察局部播放进度。
起步延迟恰好结束时不推进动画，下一次正的播放时间增量开始动画并触发首次播放回调。
补间在初始化 getter 之前捕获自己的 `time_scale`；getter 修改它时，从下一帧生效，
不会改变已经捕获的当前帧增量。

## 默认设置资产与回退通知

`TweenSettings` 是引擎原生 `DataAsset`，可以通过项目窗口创建、编辑、保存和引用，
并使用引擎现有的 Player 数据资产烘焙流程。可以在启动脚本或预加载逻辑中加载设置资产，
在创建补间前调用 `apply()`。也可以直接在脚本中配置：

```python
from infernux_tween import Ease, RewindCallbackMode, TweenSettings

settings = TweenSettings(
    default_ease_type=Ease.IN_OUT_SINE,
    default_auto_kill=False,
    rewind_callback_mode=RewindCallbackMode.FIRE_ALWAYS_WITH_REWIND,
)
settings.apply()
```

默认缓动、循环、更新阶段和回收设置影响之后创建的补间，不改写已有补间的配置。
时间缩放、安全模式和回退通知策略等管理器控制项则作用于当前管理器。
`settings.apply(manager)` 可以配置独立的 `TweenManager`。
嵌套的 `safe_mode_options` 配置日志级别和子补间失败处理。

`rewind_callback_mode` 可以直接在模块或管理器上设置：

- `FIRE_IF_POSITION_CHANGED`：只有实际回到起点才发回退通知，默认值。
- `FIRE_ALWAYS_WITH_REWIND`：重复调用 `rewind()` 也通知；倒放和平滑回退保持按位置变化通知。
- `FIRE_ALWAYS`：重复的回退、倒放和平滑回退请求都通知。

已经回到起点的 `smooth_rewind()` 不再额外翻转方向。
`rewind(include_delay=False)` 会跳过剩余起步延迟，恢复播放后直接推进动画。
设置资产的 `show_preview_panel` 控制 Tween 工具窗口的预览操作，
`show_playing_tweens` 和 `show_paused_tweens` 可以显示当前播放或暂停的补间。

## 协程等待与脚本预览

组件协程可以使用 `yield move.wait_for_completion()`，异步任务可以使用
`await move.async_wait_for_completion()`。同样支持等待开始、销毁、回退、
指定循环次数及时间位置。

传入 `return_custom_yield_instruction=True` 可以取得可复用的等待指令，
也可以直接构造 `WaitForCompletion(move)` 等对象。其只读属性
`keep_waiting` 反映当前播放状态，暂停、重新播放和销毁后都会随之变化。
指令直接交给引擎已有的组件协程调度，无需额外更新器。

```python
from infernux_tween import TweenEditorPreview

TweenEditorPreview.prepare_tween_for_preview(move)
TweenEditorPreview.start(on_preview_updated=refresh_panel)
# 在编辑器按钮或工具中结束预览并恢复目标：
TweenEditorPreview.stop(reset_tween_targets=True)
```

准备预览默认选择手动更新、清除游戏回调并关闭完成后自动销毁。
`clear_callbacks`、`prevent_auto_kill` 和 `and_play` 可以调整这些选择。
Play 模式下不会启动预览；停止后注销更新回调。
`clear_tweens=False` 会保留仍存活的已准备句柄，供下次预览使用。
插件卸载和进入 Play 时也会清理脚本预览。

## 平滑帧时间

`use_smooth_delta_time` 让自动播放使用引擎的 `Time.smooth_delta_time`。
`max_smooth_unscaled_time` 限制 Normal/Late 阶段独立时间动画每帧消耗的时间，默认约为 0.15 秒。
Late 与 Normal 共用同一帧的独立时间采样，Fixed 按物理时间倍率换算。手动更新仍使用调用者传入的时间。

```python
import infernux_tween as tween

tween.use_smooth_delta_time = True
tween.max_smooth_unscaled_time = 0.05
```

平滑器使用游戏帧的缩放时间，不使用 GPU 耗时或编辑器渲染平均值。时间倍率改变后，平滑时间会逐步过渡；需要立即冻结的动画可以显式暂停。

## 使用

第一阶段已提供脚本接口、编辑器组件和原生计算支持。使用当前引擎构建配套的 SDK，
在插件管理器导入 `infernux.tween.inxpkg` 即可使用。开发仓库提供
`examples/quick_start.py`，可以直接运行曲线、真实场景物体、序列、路径、回调和数值补间。

```python
import infernux_tween as tween
from infernux import Vector2, Vector3

move = tween.twn_local_move(transform, Vector3(80, 20, 0), 0.4)
move.set_ease(tween.Ease.IN_OUT_SINE)
tween.sequence().append(move).append_interval(0.1).append_callback(on_finished)
tween.twn_size_delta(image, Vector2(240, 80), 0.3)
```

UI 提供 `anchor_min`、`anchor_max`、`pivot`、`size_delta`、`anchored_position`、
`anchored_position3d` 和两侧的 `offset_min/max`。它们通过 `rect_transform`
访问同一个原生矩形。同一物体上的多个 UI 外观共享这个矩形；宽高表示当前尺寸，
`size_delta` 表示锚点跨度之外的尺寸差。全拉伸时，下面的 `(-32, -24)`
表示在父级宽高上各减去 32、24 像素：

```python
image.anchor_min = Vector2(0, 0)
image.anchor_max = Vector2(1, 1)
image.size_delta = Vector2(-32, -24)
image.anchored_position = Vector2(0, 0)
tween.twn_size_delta(image, Vector2(-64, -48), 0.3)
tween.twn_anchor_pos(image, Vector2(20, 0), 0.3)
```

`twn_anchor_min/max` 修改锚点，`twn_anchor_pos_x/y` 和
`twn_anchor_pos3d_x/y/z` 保留其他轴。尺寸、位置与 pivot 的批量读写使用
同一份原生状态。布局与锚点使用逻辑像素，世界 UI 按每场景单位 100 像素换算
位置；普通 Transform 位置仍使用场景单位。

绝对布局、Flow 布局、跨 Canvas 重挂、编辑器预览与撤销均已接入原生矩形状态。

函数采用 snake_case，类采用 PascalCase，枚举成员采用 UPPER_SNAKE_CASE。原生目标作为第一个参数；枚举仍传枚举，字符串端点仍传字符串。颜色使用引擎的 RGBA 列表，不添加另一套包装类型。

`to`、`to_axis`、`to_alpha`、`to_array` 创建有类型的补间。`set_ease` 接受 Ease、原生 AnimationCurve、EaseCurve 或四参数函数 `(time, duration, overshoot_or_amplitude, period)`。`set_options` 根据浮点、向量、颜色、旋转或字符串类型表达不同选项。`set_as` 复制 Tween/TweenParams 的通用设置，不复制目标或类型专用选项。

`from_(is_relative)` 的一个布尔值表示相对；`from_(set_immediately, is_relative)` 的两个布尔值分别表示立即写入、相对。不指定起点且需要延后捕获时，写 `from_(set_immediately=False, is_relative=False)`。指定值的 `from_(value, set_immediately=False, is_relative=True)` 在调用时固定端点，只延迟写入。`change_start_value`、`change_end_value`、`change_values` 的时长参数为 `new_duration`；`goto(seconds)` 不包含开始延时。

在开始播放或插入序列前配置。序列支持嵌套、插入/前置/并行回调、间隔和增量循环。回调里的暂停、跳转、销毁会终止当前调度。实例控制一个补间；模块筛选控制必须传目标或 ID；`*_all` 明确操作全部。`set_link` 关联 GameObject 生命周期，暂停的补间也会清理。

快捷操作覆盖 Transform、Rigidbody、材质、UI、精灵/线条、相机、光照和音频。刚体 Move/Rotate/LookAt/Jump/Spiral 沿用管理器的更新阶段，刚体路径明确选择 Fixed。其它刚体补间需要自动按物理步播放时，请配置 `set_update(UpdateType.FIXED)`。位移/旋转通过 move_position/move_rotation 应用。Graphic 淡出修改颜色 alpha，UIGroup 修改 alpha，AudioSource 修改音量。材质命名属性的参数放在 duration 前。路径有局部/世界坐标、朝向、路点回调、跳转与 Gizmo。Jump/Punch/Shake/Spiral 和混合动画复用同一时钟。引擎尚无的文本描边发光、整体 UI Transform 缩放等不会用无效字段冒充；详细边界见仓库 README。

添加「Tween Animation」「Tween Path」「Tween Visual Manager」即可使用原生 Inspector 字段与场景路径手柄。打开「动画 / Tween」进行可恢复预览，保存、撤销、切换选择和进入 Play 都会还原创作值。持久事件使用原生列表、引用与 Undo，精确关联组件实例；不可表达的参数类型不会被伪装成字符串。预览不发送游戏回调。

作者事件的 `has_on_*` 默认关闭，公开事件默认 `None`。在 Inspector 中启用对应
事件后添加条目；脚本则在创建 Tween 前设置标志和 UIEvent：

```python
from infernux.ui.ui_event import UIEvent

animation.has_on_complete = True
animation.on_complete = UIEvent()
animation.on_complete.add_listener(on_finished)
animation.create_tween()
```

创建后修改开关或替换事件对象，不会替换已绑定的回调，需要重新创建 Tween。
关闭的播放事件在创建时清空；Tween Created 只控制是否调用。保存只保留作者条目
和事件是否为空，不保留 `add_listener` 注册的运行时函数。旧代码不能再依赖事件
自动启用；销毁后 `animation.tween` 为 `None`，重新启用物体也不会自动重建已销毁的 Tween。

动画的 `target` 保存实际组件引用，`target_go` 保存目标物体，`target_is_self`
决定使用自身还是目标物体。`tween_target_is_target_go` 决定批量控制的分组，
不会替换实际组件。世界移动操作组件；局部移动、局部旋转和缩放操作目标物体的
Transform。新组件默认无动画且尚未通过创作验证，脚本可这样明确配置：

```python
animation.animation_type = animation.AnimationType.MOVE
animation.target_is_self = False
animation.target_go = actor
animation.target = actor.transform
animation.target_type = animation.TargetType.TRANSFORM
animation.animation_valid = True
animation.end_value_v3 = (4, 0, 0)
animation.create_tween(and_play=True)
```

`animation_valid` 是创作有效标志；原有 `is_valid` 仍表示引擎组件存活。
编辑器会对可确定的目标执行创作验证。不要把这两个含义混用。
使用 `end_value_transform` 和 `use_target_as_v3=True` 可从另一个 Transform
读取终点世界坐标，创建时取消相对模式；空终点按零坐标处理。`end_value_rect`
接受引擎 Rect，其他公开终点包括 `end_value_float/v2/v3/color/string`。
这些名称与原有 `end_value/end_size/end_vector/end_color/end_text` 共用存储。

`is_active` 只控制自动生成，手动创建仍可执行。普通动画在 Awake 生成，
使用 Transform 终点的移动延后到 Start，避免过早读取终点位置。反复启用物体
不会再自动生成。创作无效时，请求重新创建也会保留现有补间。
Color/Fade 取消相对模式；灯光的 Fade 修改亮度。六种 Camera 动画覆盖宽高比、
背景色、视野角、正交大小、像素矩形和归一化视口，支持 From 与相对模式。
部分特殊目标和 UI 能力仍待实现，不能将枚举存在视为完整兼容。

`TweenPath.path` 是当前路径对象。已烘焙的作者路径使用世界坐标；局部路径启动后，
公开对象反映转换后的局部坐标。`get_draw_points()` 返回路径自身的坐标，
`get_world_draw_points()` 明确转换为场景绘制坐标。曲线路径的绘制点密度与
用于距离估算的 `path_resolution` 分开。运行中的坐标转换不会写回作者配方。
组合旋转约束可用 `AxisConstraint.X | AxisConstraint.Y`，保存和恢复会保留组合。
未选择朝向目标时仍可沿路径运动，并保留原朝向。

```python
characters = tween.TextTweenAnimator(label)
characters.twn_offset_char(0, Vector3(0, 12, 4), 0.4).from_()
characters.range().twn_fade(0, 0.4).from_()
```

索引采用原生字素，位移、Euler 角和缩放是真正的 Vector3，正 Y 与 Transform 一样向上。逐角偏移保留 XYZ；区间倾斜包含终点。这些操作占用 Manual 层，与 Text Animator 的 Effects、Appearance 层按顺序组合。布局变化会终止旧索引动画；一轮管理器更新只提交一次共享缓冲。`reset`、`dispose` 还原这一层。

插件自行管理更新注册，空组或全部暂停时没有活动更新。Manual 补间只由 `manual_update(scaled_delta, unscaled_delta)` 驱动，独立时钟采用不受缩放的时间。`get_time_scale`、`set_time_scale` 控制默认管理器。Spring 是独立的有状态弹簧辅助类，在自己的模拟时钟中调用 pull、animate 和 update。

自定义插值器继承 `AbsTweenPlugin[外部值类型, 存储类型, 选项类型]`，并使用
`to(plugin, getter, setter, end_value, duration)` 创建。返回的 `TweenerCore`
提供 `start_value`、`end_value`、`change_value`、`plug_options`、`getter` 和
`setter`。外部值与内部存储可以不同，不要求存储对象支持通用四则运算。
Python 值对象可用 `storage_default` 指定新默认值的工厂；默认 `None` 用于引用存储。

插件实现 `convert_to_start_value`、两种 `set_from`、`set_relative_end_value`、
`set_change_value`、`get_speed_based_duration`、`evaluate_and_apply` 和 `reset`。
每个补间的状态保存在自身值与选项中，共享插件对象应保持无实例专用状态。
直接调用内置插件的 `evaluate_and_apply` 时，使用传入的 `elapsed` 与 `duration`，
不推进或重设补间自身的时钟。值参数和选项在缓动回调之前确定；回调中的修改影响
后续调用。分段数组保留共享存储，数组元素在回调中的修改会参与本次插值；
缓动函数收到该段的局部时间与段时长。
选项需要无参构造及 `reset()`；替换整组选项会复制字段，直接修改补间的选项
字段则只影响该补间。销毁与回收调用插件和选项的 Reset，插件负责释放存储中的引用。

插件可通过 `EaseManager.evaluate(tween, elapsed, duration, amplitude, period)`
使用当前缓动；也可使用指定 Ease 和回调的重载或 `to_ease_function` 工厂。
`ease_overshoot_or_amplitude`、`ease_period` 是可直接修改的公开参数。
两个 `INTERNAL_*` Ease 是内部状态：自定义缓动应传曲线或函数，单独选择
`INTERNAL_CUSTOM` 而不提供回调会失败。

补间的 `id`、`string_id`、`int_id` 分别保存对象、字符串和整数 ID，可以同时
存在。`set_id("menu")`、`set_id(7)` 自动选择字符串和整数通道；要明确使用
对象通道，写 `set_id(object_id=value)`。32 位之外的整数作为对象 ID。
筛选也按类型选择通道；布尔、整数和浮点对象不会被当成同一个 ID。
`set_as` 复制全部 ID，保留接收方目标；销毁清空 ID 和目标。
`TweenParams.params.clear()` 提供可复用的共享配置对象。

链式注册仍用 `on_play(...)`、`on_update(...)` 等方法；原始回调字段使用
`play_callback`、`update_callback` 等名称，赋值 `None` 即清空。
对应字段还有 `start_callback`、`pause_callback`、`rewind_callback`、
`step_complete_callback`、`complete_callback`、`kill_callback`、
`waypoint_change_callback`。可写方向字段为 `backwards`，`is_backwards()`
继续查询有效补间的方向。这样不会把同名注册方法误当成数据字段。

销毁和类型池复用后会保留 Pause 回调；需要释放它捕获的对象时，
在回收前写 `pause_callback=None`。
调试目标名称由 `debug_mode`、`use_safe_mode`、`debug_store_target_id` 共同
控制，三者都开启才记录，销毁后清空。完整日志与报告功能仍待补齐。

图像填充使用引擎的真实几何绘制，先为 UIImage 指定纹理并设置填充类型：

```python
image.image_type = image.Type.FILLED
image.fill_method = image.FillMethod.RADIAL360
image.fill_origin = 0
image.fill_clockwise = True
tween.twn_fill_amount(image, 0.75, 0.4).set_ease(tween.Ease.IN_OUT_SINE)
```

支持水平、垂直、90/180/360 度径向填充。先设置方式，再设置起点，修改方式会
重置起点为零。UV 保持原图位置，旋转和镜像围绕完整图像中心。快捷函数与
Tween Animation 的 `FILL_AMOUNT` 均支持 From 和相对模式，预览结束会还原值。
没有纹理时继续显示完整背景矩形，默认命中区域也保持矩形。新功能需要相应
引擎 SDK，不能在旧 runtime 上仅更新插件来获得原生绘制能力。

在 UIFrame 的自动布局中，可以补间最小尺寸、首选尺寸和伸展权重。先把
UILayoutElement 添加到已有 UI 控件；无视觉的占位物体可以使用 UIFrame。

```python
from infernux.ui import UILayoutElement
import infernux_tween as tween

layout = panel.game_object.add_component(UILayoutElement)
layout.min_width = layout.min_height = 0
layout.preferred_width, layout.preferred_height = 120, 60
layout.flexible_width = layout.flexible_height = 0
tween.twn_preferred_size(layout, (200, 60), 0.4).set_ease(tween.Ease.IN_OUT_SINE)
```

`twn_min_size` 修改最小尺寸；`twn_flexible_size` 修改横纵伸展权重，权重不是
像素值。这三个函数都支持 snapping、From 和相对模式，目标是 UILayoutElement。
最终矩形由父布局根据其他子项与可用空间决定；补间不会直接改写控件的 width、
height 或 Transform。负数表示不提供该项输入，零权重明确禁止伸展。同物体有
多个输入组件时，每项属性独立按优先级选择，同优先级取最大值。

现有未添加输入组件的 Fixed/Hug/Fill 控件保留原有语义。此功能依赖匹配的引擎
SDK；它没有添加完整 Unity RectTransform，锚点与 Pivot 补间仍待实现。

Punch 在启动时固定为 OutQuad，`set_relative`、`set_speed_based` 以及启动前
设置的其他 Ease 会被参照所规定的启动过程覆盖。它使用分段位移，不再使用
正弦近似。高层 `twn_punch_*` 在时长不大于零时返回 None。

Transform 的 `twn_jump` / `twn_local_jump` 返回 Sequence，初始使用管理器的
默认 Ease；需要横向匀速时，显式 `.set_ease(tween.Ease.LINEAR)`。目标高度
偏移也有自身的缓动，不能用单条直线加正弦来替代。连续播放与拖动进度都经过
实际参照对照；刚体路径仍需要单独的物理步进验证。

Shake 使用引擎共享随机流。需要复现一段效果时，保存随机状态再创建补间：

```python
from infernux import Random
import infernux_tween as tween

Random.init_state(123)  # 通常在会话开始时设置一次
checkpoint = Random.state
effect = tween.twn_shake_position(target, 0.4, strength=0.2)

# 需要重新生成同一段随机效果时恢复；一般播放无需每帧恢复。
Random.state = checkpoint
```

同一个补间拖动进度、回退或重播时复用已有分段，不再次消耗随机数。不同补间
会继续推进共享流。相机的标量 Shake 在相机局部平面内运动，向量强度可以产生
空间偏移；相机局部旋转在启动时读取。Full/Harmonic、衰减和分段时长已有实际
参照检查。新功能需要包含原生 Random 接口的匹配引擎 SDK。

Spiral 通过通用自定义插件流程执行：Transform 使用局部位置，Rigidbody 使用
世界位置。`frequency` 会影响半径，`depth` 表示沿旋转轴前进的距离。零轴向或
极小轴向回退到前方；零速度使用快捷操作的默认值。正常运动建议使用正频率。
相对模式不会把起点加到轴向上，From 也不提供反向螺旋播放。缓动和更新阶段
沿用管理器默认值；需要匀速或固定物理步时，明确配置：

```python
effect = tween.twn_spiral(body, 2.0, Vector3(0, 0, 1),
                          tween.SpiralMode.EXPAND_THEN_CONTRACT,
                          speed=0.75, frequency=5.0, depth=2.0)
effect.set_ease(tween.Ease.LINEAR).set_update(tween.UpdateType.FIXED)
```

公开的 `SpiralPlugin.get()` 与 `SpiralOptions` 也可以用于
`to(plugin, getter, setter, axis, duration)`，复用 `TweenerCore` 的生命周期与对象池。

自定义插件可调用
`EaseManager.evaluate_unclamped(t, time, duration, overshoot_or_amplitude, period)`，
获取包含增量循环的缓动因子，再按 `start + change * factor` 等插值规则计算。
它计入子项和直接父序列的增量；更外层序列负责驱动时间，不重复叠加数值偏移。


## 路径编辑

路径检查器支持默认、仅信息与路点、开发者、仅路径四种模式。
“仅路径”保留几何数据，不自动创建补间，也不会被工具面板启动预览。
手柄支持自由拖动或 XYZ 轴约束；缩放可选固定屏幕大小或世界空间大小。
序号与分段长度可以单独显示；关闭实时预览时，拖动过程保留旧路径显示，
提交后刷新。拖动、列表编辑和贴地都通过引擎的撤销系统处理。

“路点贴地”从当前路点向世界 Y 负方向查询碰撞表面，偏移沿世界 Y 应用。
没有命中的点保持原位，不移动路径所属物体。已烘焙路径的路点使用世界坐标，
修改时同步路径配方；普通未烘焙路径仍支持局部和相对坐标输入。


## 运行状态与矩形坐标

`version` 是当前安装的插件版本。默认管理器尚未初始化，或执行
`clear(destroy=True)` 后，`instance` 为 None；其余时间返回实际管理器。
设置 `draw_gizmos = False` 可以跳过运行时路径辅助线的几何准备和绘制，
编辑模式的路点手柄仍可使用。

`switch_to_rect_transform(source, target)` 返回对齐两个矩形中心所需的目标
锚定位置，包含拉伸尺寸、枢轴、目标平面投影和世界 UI 单位换算。
调用本身不会赋值位置。源矩形中心偏移采用未旋转的屏幕坐标，
这个接口不用于任意相机之间的投影转换。

```python
position = tween.switch_to_rect_transform(source_image, target_image)
tween.twn_anchor_pos(target_image, position, .4)
```


## 可选目标接口与编辑器报告

滚动组件可以提供可读写的 `normalized_position`（Vector2）、
`horizontal_normalized_position` 和 `vertical_normalized_position` 属性，
分别使用 `twn_normalized_pos`、`twn_horizontal_normalized_pos` 和
`twn_vertical_normalized_pos`，均支持可选的 `snapping=False`。
组件负责裁剪、边界、输入和布局更新；这些快捷操作负责补间播放，
不会凭空创建一个滚动控件。

`twn_set_float(target, float_name, end_value, duration)` 使用返回数值的
`get_float(name)` 和 `set_float(name, value)`。参数暴露、单位、参数不存在时
的处理和音频线程发布均由目标负责。材质参数也支持此接口，
但这个接口本身不等于完整的混音器资产或效果图。

设置 `show_editor_report = True` 后，编辑器退出 Play 时会打印根补间与
序列的峰值数量、已处理错误数量。`get_editor_report()` 可以直接读取统计。
计数发生在对象归属变化时，不需要每帧遍历补间。

## 单精度数值

普通 Python 浮点终点使用双精度补间。需要明确使用单精度时，把终点写为
`numpy.float32`；回调收到的值也保持这个类型，相对值、From 和循环使用同一精度。

```python
import numpy as np

value = [np.float32(0)]
handle = tween.to(lambda: value[0], lambda v: value.__setitem__(0, v), np.float32(1), .5)
handle.set_options(snapping=False)
```

单精度和双精度的数值吸附都在原生采样器中计算。修改数值或选项时更新计算缓存，
播放时不重复转换输出类型。批量单精度采样可直接写入已有的 `float32` 缓冲区，
大批量计算期间释放 GIL。

显式标量还支持 `numpy.float64`、`int32`、`int64`、`uint32` 和 `uint64`。
终点选择类型，回调和直接修改数值时保留同一类型；批量采样写入相应类型的缓冲区。
类型和采样入口在配置时绑定，播放时不重复识别。

`uint32` 使用 `UintOptions.is_negative_change_value` 保存变化方向。

矩形和字符串补间也提供与标量相同的核心字段。矩形保持 `Rect` 类型，
保留用户原本的 getter/setter；`RectOptions.snapping` 在原生层处理四个字段的取整。
`StringOptions` 提供 `rich_text_enabled`、`scramble_mode` 和 `scrambled_chars`。
复制字符串选项时共享字符数组；修改数组时更新关联的文本执行计划，播放时不扫描数组。
直接修改 `start_value`、`change_value` 会保留启动时的文本长度缓存；
需要重建整个变化过程和长度缓存时，使用 `change_values`。

`to_array` 通过原生 `Vector3Array` 暴露逐段的 `start_value`、`end_value` 和
`change_value`。创建时复制输入终点；启动后直接修改终点不会重新计算变化量，
需要重建变化过程时使用 `change_values`。修改起点或变化量的数组元素、元素坐标，
会直接进入已准备的原生采样器。批量采样先保存一份稳定数据，再释放 GIL；
并发编辑影响后续的计算。`Vector3ArrayOptions` 保留声明的轴约束和取整选项。

欧拉旋转补间提供 `QuaternionOptions`，包括 `rotate_mode`、`axis_constraint`、
`up`、`dynamic_look_at` 和 `dynamic_look_at_world_position`。getter/setter 使用
四元数，核心起点、终点和变化量使用欧拉角 `Vector3`。普通旋转和两种轴叠加模式
共用原生采样；动态 Look At 更新原生终点和变化量，逐帧复用已有采样器。
批量四元数采样先固定输入，大任务在原生计算期间释放 GIL。

旋转快捷接口在创建时已确定类型。通用 `to` 使用 `Vector3` 终点时，若在启动前
查询插件或选项，会优先读取 getter 的返回类型注解；没有注解时，会读取一次 getter，
区分向量补间与四元数旋转。启动时仍重新捕获当前值。
使用 `def read_rotation() -> quatf:` 这样的声明，可直接提供类型信息。
`uint64` 的原生十进制运算保留大整数位；结果超出其值域时按 `use_safe_mode`
与现有的定位、逐帧更新规则处理，不引入 Python 十进制计算或其它数值库。

普通 `Vector2`、`Vector3`、`vec4f` 补间也直接读取原生起点和变化量。
例如 `handle.start_value.x = 5` 或 `handle.change_value.y = 40` 会影响后续采样，
并复用已有的计算任务。传入或重新赋值整个向量时复制其值；修改调用者保留的
原始向量不会改变补间。直接改终点不会重新计算变化量，重新定义过程使用
`change_values`。批量采样在释放 GIL 前固定本批输入；并发修改从下一次采样生效。
普通 Python `int`、`float` 及其类型标注继续可用，无需自行使用 NumPy 类型。

路径补间提供 `PathOptions` 和 `PathPlugin.get()`，并共享 `TweenerCore` 的
起点、终点、变化量、getter、setter 和选项接口。可以使用
`Path(PathType.CATMULL_ROM, waypoints, 10)` 定义待生成的路径，再通过显式插件
调用 `to`。启动时生成长度表和原生控制点；修改控制点会保留原来的长度表，
原生采样直接读取新坐标。`Path.compile()` 返回按当前几何重新计算长度表的
独立快照，可以用于释放 GIL 的批量计算。

直接替换路径补间的起点或终点不会替换正在采样的变化路径。
`change_end_value` 会生成新的终点路径并更新变化路径；路径查询接口读取终点路径。
`PathOptions` 包含模式、朝向、位置和旋转轴约束、闭合、局部空间、目标及启动状态。
复制选项时复制向量和四元数的值；替换选项会与旧选项解除关联。

生成后的贝塞尔路径用 `wps` 保存端点，用 `control_points` 保存
`ControlPoint(a, b)` 数组；`points` 保留编辑工具使用的展开视图。这些接口读取
同一份原生数据，修改坐标会直接影响后续采样。替换 `wps` 或 `control_points`
数组时保留原有长度表和另一组数组；原生数组引用可以共享，旧数组视图保持有效。
批量采样固定端点和控制点两组输入后释放 GIL。

`control_points = None` 表示没有控制点数组，`control_points = []` 表示存在一个
长度为零的数组。非线性采样分别产生空引用与越界错误，不会自动补全数据。
增量循环在进入不同循环时按当前端点生成平移副本；同一循环复用已有副本。
若要让编辑后的坐标影响新的循环，可以直接修改原路径的端点和控制点。
副本由 `Path` 持有：多个补间共用同一个路径时，也共用它的循环缓存和生命周期。
需要独立修改、循环或销毁的动画应分别创建路径。直接调用路径插件时，使用传入的
`change_value` 所持有的缓存，不会借用补间原有路径的副本。

`PathPlugin.get().set_orientation(options, tween, path, path_percentage, t_pos, update_notice)`
可以独立设置路径朝向，不推进时间、不写入位置，也不触发补间回调。
`path_percentage` 是路径长度映射之后的归一化参数，`t_pos` 是本次路径位置。
它支持以 Transform、GameObject 或 Rigidbody 为目标的普通补间与序列；
传入的选项保持不变。最小前视距离由 `PathPlugin.min_look_ahead` 提供。

暂停和恢复保持补间的创建顺序。setter 对后续补间数据的修改在本次更新中生效；
setter 安装、替换或清除自己的更新回调，也会影响本次回调分发。
序列跨越循环边界时会逐次应用边界和当前位置，不合并可观察的 setter 调用。
子补间的方向反映本次序列区间的遍历方向，可能与根序列的播放方向不同。

`Path.wp_lengths` 是包含首项的各段长度数组，使用固定长度的 `Float32Array`。
它支持普通数字、逐项修改和可写 `memoryview`；也可以用列表替换整组数据。
修改长度会影响 `goto_waypoint` 和路点回调，不重建路径几何或采样长度表。
增量循环副本共享当时的数组；之后替换原路径的数组不会替换已有副本的引用。
路径销毁后字段清空，已经取得的数组或缓冲区视图仍然有效。

自定义路点长度可能产生负播放时间。正向播放会保留这段时间，跨过零点后正常继续；
反向播放会回到零点并暂停。恢复过程中仍会触发生命周期和循环通知。
Yoyo 的方向切换要求实际存在循环，只播放一次时不会因选择 Yoyo 而反向。

时间跳转也会触发路点回调。暂停或重新定位时间不会自动取消当前路点批次，
Rewind 产生的新通知可以嵌套其中。每条通知读取当时的回调，替换回调会在同一批次生效。
清除回调（包括立即销毁导致的清除）后，剩余调用按所配置的异常策略处理。
关闭安全模式后，异常直接向外抛出，不自动销毁失败句柄。

直接调用 `PathPlugin.evaluate_and_apply` 时可以传入普通补间或序列。
调用使用传入的时间、时长、方向和跨循环次数，将路点状态与回调写回实际补间，
不推进它的时间，也不替换它原有的插件选项。已生成的路径不需要再次调用 getter。
自定义 setter 或缓动函数对路径选项的修改影响后续采样；本次采样使用进入调用时的值。
setter 修改补间的目标引用时，本次朝向计算使用修改后的目标。
只有等待区间的序列需要生命周期或更新回调才能启动；单独的路点监听不构成时间线内容。

已有补间在暂停、恢复和切换更新阶段后保持创建顺序。回调可以让排在后面的已有补间
在本次更新中恢复执行；新建补间从下一次更新开始。更新期间调用 `kill()` 会先标记失效，
再延后回收：尚未访问的位置可以在本次更新结束时回收，已经访问的位置等待下一次所属阶段。
销毁回调和对象池复用发生在回收时，同一批次按访问顺序的反向执行。
全局 `clear()` 直接注销根补间并清空对象池，保留旧句柄上的字段，不递归销毁序列子项，
也不补发已经失效的根补间所等待的销毁回调。
