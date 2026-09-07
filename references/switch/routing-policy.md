# MindPlus-Switch 路由与敏感节点

本文件是第一版 Mode Registry。它只决定是否进入某个转换分支，不定义积木转换细节。

## Mode Registry

| mode_id | status | V1 结构特征 | V2 `config.mode` | 资料入口 |
| --- | --- | --- | --- | --- |
| `UPLOAD` | `SUPPORTED` | `arduinoC/main.ts` | `upload` | `upload-mode.md` |
| `PYTHON_BLOCK` | `SUPPORTED` | `python/main.ts` | `python-block` | `python-block-mode.md` |
| `REALTIME` | `PLANNED` | 未注册的实时模式特征 | — | — |
| `MICROPYTHON` | `PLANNED` | 未注册的 MicroPython 特征 | — | — |

目录名相似不能代替注册表特征。`isDevice: true` 主控扩展、纯 Python 包和 MicroPython 库不进入当前两个分支。

## 路由顺序

1. 先读取 V1 根目录的 `config.json` 和已注册的入口特征，不先加载模式教程。
2. 记录每个候选的相对路径和确定性结果：`C3` 为实际文件/字段或脚本结果，`C2` 为打包行为/截图/Builder 实例，`C1` 为已校验资料，`C0` 为推断。
3. 只有一个 `SUPPORTED` 候选且没有强制审核标记时继续。用户明确给出的模式必须与源事实一致。
4. 两个候选都是 C3 时属于并列，不因 `AUTO` 而猜测；写入日志并等待用户选择。两种模式需要两个独立 run。
5. 命中 `PLANNED` 或未知结构时停止为 `BLOCKED/UNSUPPORTED_MODE`，不能降级到上传或 Python。

任务策略：

- `AUTO`：默认。唯一最高置信度、语义不变且没有基线强制审核时继续。
- `SENSITIVE_REVIEW`：遇到任何敏感节点都暂停询问。

运行过程中不得修改本文件或任何状态表。

## 默认敏感节点

遇到以下任一项，写入 `log.md` 的候选、证据、影响和问题；AUTO 也不能绕过基线标记为强制审核的项：

1. 多个模式同时命中或证据并列。
2. 源码、`.mpext`、截图、菜单或目标样例冲突。
3. 必须改变 opcode、function、积木类型、参数 key/order 或生成语义。
4. 必须改变 `author`、旧 `compatibilityId`，或无法证明旧身份。按共享规则将非法 V1 `id` 确定性规范化为 V2 ID 不单独触发审核，但规范化为空、冲突或包身份不一致时必须暂停。
5. 缺少封面、图标、库、依赖或版本信息，需要生成、猜测或选择替代值。
6. `board/boards`、`supportDevices`、`supportArch` 无法形成可靠映射。
7. 需要使用本地基线未记录的字段、Runtime 或 Generator API。

依赖版本推断属于第 5 项；视觉资源重画也属于第 5 项。缺少关键事实时停止，不把 C0 推断写成决定。

