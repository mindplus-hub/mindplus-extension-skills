# REALTIME：实时模式

用于 V2 创建、V1 自动转换、升级和审核，`config.mode` 为 `realtime`，新目录使用 `ext2-rt-`。支持模块扩展和舞台扩展，不包含主控扩展。V1 默认源码入口为 `javascript/index.js`，也支持 `asset.javascript.dir/main` 指向的实际入口；官方模板只提供 index.js 而声明构建后的 main.js 时，盘点器使用 index.js。

通过 `select_reference_topics.py --mode REALTIME` 选择并校验 `realtime.*` 与共享主题，只读取返回的资料。

- 模块扩展的 `isSupportStage` 为 false 或省略，`supportDevices` 必填且非空；舞台扩展须显式设置 `isSupportStage: true` 并省略 `supportDevices`。创建规格用 `is_support_stage` 表达此选择，默认模块；不添加 `libraryConfig` 或 `supportArch`。
- `index.js` 的 `getPrimitives()` 返回 Func，不能使用 `getCodePrimitives()`。方法为 `opcode(args, util)`，直接执行并返回值或 Promise，不产生 Arduino／Python 代码。
- 硬件模块按文档通过 `runtime.getDevice()` 取设备；检查连接，使用 Firmata 的引脚转换表。并发串口写入按文档用 `serialWriteIsAvailable()` 和 `util.yield()` 等待。不要把舞台能力当成所有设备都提供的接口。
- Firmata 的数字／模拟、PWM、I2C、串口 API 读取 `realtime.firmata`；舞台扩展读取 `realtime.stage`，仅使用已记录的 runtime 能力。
- 双语文本、菜单、资源和 README 按共享规则处理；静态检查使用 `check_converted_extension.py --mode REALTIME`，创建时输入由规格适配器生成的 inventory。

静态、Builder 构建、积木显示和实际执行分别记录；硬件模块还需区分连接、Firmata／通信及设备响应证据。

## V1 自动转换

1. 按 [转换流程](../workflows/switch.md) 选定 `REALTIME`，读取 `getInfo()`、`v1_entry_inventory.REALTIME.block_functions`、执行方法、imports 以及资源。盘点只读源码，不加载或执行旧库。若 blocks 来自 import、动态计算或生成文件，继续追踪实际定义并补齐 inventory 与证据；不能把空扫描当作没有积木，也不能漏掉 helper 文件。
2. V1 JavaScript 类的 getInfo 移到 V2 `index.js`，执行逻辑与状态放到 Func 或保留的本地 helper。用 `getPrimitives()` 绑定 Func；按旧 opcode 保留同名 `(args, util)` 方法，参数从 args 读取，不改成 `(generator, block, parameter)` 或返回代码字符串。
3. 保留 command／reporter／boolean／hat 的类型、真实返回值、Promise／async 完成时机、`util.yield()` 的重试条件、事件注册及清理。旧构造器中 runtime 与扩展 ID 的注入关系仍绑定本次 V2 实例；this 的状态归属、外围对象、定时器、监听器及 dispose 不能因拆文件而丢失。
4. 保留菜单实际 value、参数类型／默认值、图标与二级结构；对积木和菜单显示文字使用稳定 formatMessage 与双语资源。旧 `module.exports`、Scratch 内部导入或硬编码的旧扩展 ID 不能直接冒充 Builder 的模块/API，按当前实时与 runtime 主题改写；缺口按 official-corpus 回退查证，不凭空发明接口。
5. 根据明确的配置、板卡及实际设备调用判定模块／舞台，记录来源。`isSupportStage` 的布尔源值可由配置骨架保留；没有这个字段不等于舞台。模块补齐非空 `supportDevices`，舞台显式 true 并省略主控范围。无法从源码确定时只询问这个具体决定。
6. 本地 helper、图标、资源和声明的外部依赖按来源迁移，JavaScript 依赖不写入 Python requirements。代表性对照只覆盖本次涉及的同步／异步值、事件或等待路径；静态、快照／复制校验、构建与 Basic 复用共享转换流程的结果，不追加一轮。未连接设备不宣称硬件已验收。
