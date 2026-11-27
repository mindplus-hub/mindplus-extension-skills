# V2 `config.json` 契约

本文件是当前 MindPlus-Switch 的配置生成约束，和机器检查用的
[`config-schema.json`](config-schema.json)保持一致。它只覆盖目前支持的
`UPLOAD`、`PYTHON_BLOCK`、`MICROPYTHON`、`REALTIME` 四种 V2 模式，创建、转换、升级与审核均按选定模式使用。每种模式使用独立 profile，不能混用字段。

## 规则

1. 先按选定模式读取 schema，再从 V1 证据填值。不要从 V1 `config.json` 原样复制顶层结构。
2. 顶层键必须是该模式 `allowed_fields` 的子集，必须包含 `required_fields`；其它键一律删除并在日志中记录。
3. V1 的 `email`、`license`、`isBoard`、`platform`、`asset` 是旧格式字段，不属于 V2 `config.json`。
4. 字符串字段没有可验证描述时写 `""`，不得用模型知识、样例值或最新版补全。`meta.runtimeVersion` 没有实际 Runtime API 证据时为 `""`，但 `meta` 和 `runtimeVersion` 仍保留。留空是契约要求的结果，不是缺陷：必需字段已出现即为合规，“必填项缺失”只指字段不存在、类型不符或固定值不符，不能因为值为空字符串而在审核中定级。
5. 结构型字段既不能机械写空值，也不能因为"没有用到 Runtime 引脚 API"就整体省略。`supportDevices` 与 `supportArch` 是**设备兼容范围声明**，与是否调用 `getBoardPinsByType` 无关：UPLOAD 必须给出非空设备范围，二者至少出现一个（`supportArch` 存在时覆盖 `supportDevices`）。板卡证据来自 V1 的 `asset.arduinoC.board` 等声明，不是引脚 API 的使用情况。空的 `supportArch` 会覆盖设备范围，不能当作普通空字符串。
6. `compatibilityId` 仅在确认需要兼容已有 V1 库时填写；普通新建保留 `""`，不从新作者或新 ID 自动生成。V1 转 V2 的兼容迁移中，能从 `.mpext` 或 V1 `author`/原始 `id` 证明时必须填写预期的小写旧身份；身份无法证明时停止，不猜值。

## 当前精确字段集

`required_fields` 是每次转换都必须出现的固定集合；`optional_fields` 是允许出现、但必须有证据且非空的集合。检查器会拒绝白名单之外的字段并检查 JSON 类型。

### UPLOAD

必需字段：

```text
id, version, name, description, author, compatibilityId, cover,
isDevice, sku, main, mode, libraryConfig, supportDevices, meta
```

允许的附加字段：

```text
supportArch
```

`supportDevices` 必填且非空（官方 Wiki 将模块扩展的该字段标为必填）；整架构范围的扩展改用 `supportArch`，
此时 `supportArch` 必填且非空、并覆盖 `supportDevices`。二者都不出现不是合法配置。

固定值是 `mode: "upload"`、`isDevice: false`、`main: "main.js"`。没有外部全局 Arduino 库时
`libraryConfig` 为 `[]`；本地复制到 `public/libraries/` 的库不能因此加入该数组。`supportArch`
出现时会覆盖 `supportDevices`，两者的选择必须来自 V1 的板卡证据。`supportArch: ["all"]`
是支持所有主板的合法非空声明；审核现有库时不能将它当作空数组、非法架构或缺少主板列表。

### PYTHON_BLOCK

必需且唯一的顶层字段集：

```text
id, version, name, description, author, compatibilityId, cover,
isDevice, sku, main, mode, meta
```

固定值是 `mode: "python-block"`、`isDevice: false`、`main: "main.js"`。Python 依赖不进入
`config.json`，只按 Python Reference 中的两个权威 V1 来源生成 `public/requirements.txt`；因此
`libraryConfig`、`supportDevices`、`supportArch` 都不能添加。

## MICROPYTHON 与 REALTIME

两者沿用 PYTHON_BLOCK 的基础字段、`isDevice: false` 和 `main: "main.js"`，但分别固定
`mode: "micropython-block"`、`mode: "realtime"`，不允许 `libraryConfig` 或 `supportArch`。

- MICROPYTHON：额外必需 `supportDevices`，必须是非空对象。本地库与可选 requirements 按 MicroPython 资料处理，不使用 Python V1 的依赖来源规则。
- REALTIME：允许布尔值 `isSupportStage`，省略时按 false。模块扩展必需非空 `supportDevices`；舞台扩展必须 `isSupportStage: true` 并省略 `supportDevices`。检查器按这两个分支校验，不把主控设备扩展混入此模式。

## 值的来源顺序（创建与转换）

以下旧身份来源规则适用于 CONVERT；CREATE 使用已冻结规格，作者按 [author-identity.md](author-identity.md) 选定和规范化。UPGRADE 保留已有作者，除非本次明确要求修改署名。

`id` 使用规范化后的 V2 小写字母数字 ID；`compatibilityId` 使用旧包身份；`author`、`version`、
`name`、`description` 和 `sku` 只使用 V1 文件或已记录的用户证据；`cover` 指向目标 `public/`
中的实际封面；`meta.runtimeVersion` 只使用已加载 Topic 明确给出的 Runtime 最低版本。来源缺失的
字符串写 `""`，身份、入口或模式固定值无法满足时进入敏感节点，不以空值掩盖问题。

在新 Builder 根目录上先运行 `scripts/switch/create_config_skeleton.py` 生成固定字段骨架，再补充有证据
的值；不要直接手写一份脱离 profile 的配置。生成后必须运行
`scripts/switch/check_converted_extension.py`。字段不匹配、类型不匹配、固定值不匹配或 V1 字段泄漏都在
`npm run build` 前阻断。
