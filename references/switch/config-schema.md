# V2 `config.json` 契约

本文件是当前 MindPlus-Switch 的配置生成约束，和机器检查用的
[`config-schema.json`](config-schema.json)保持一致。它只覆盖目前支持的
`UPLOAD` 与 `PYTHON_BLOCK` 两条 V1→V2 路由；新增模式时必须先增加独立 profile，不能把
未来模式的字段混入当前配置。

## 规则

1. 先按选定模式读取 schema，再从 V1 证据填值。不要从 V1 `config.json` 原样复制顶层结构。
2. 顶层键必须是该模式 `allowed_fields` 的子集，必须包含 `required_fields`；其它键一律删除并在日志中记录。
3. V1 的 `email`、`license`、`isBoard`、`platform`、`asset` 是旧格式字段，不属于 V2 `config.json`。
4. 字符串字段没有可验证描述时写 `""`，不得用模型知识、样例值或最新版补全。`meta.runtimeVersion` 没有实际 Runtime API 证据时为 `""`，但 `meta` 和 `runtimeVersion` 仍保留。留空是契约要求的结果，不是缺陷：必需字段已出现即为合规，“必填项缺失”只指字段不存在、类型不符或固定值不符，不能因为值为空字符串而在审核中定级。
5. 结构型可选字段不能机械写空值：`supportDevices`、`supportArch` 只有对应 V1 板卡证据与当前模式文档支持时才出现；没有证据就省略。空的 `supportArch` 可能覆盖设备范围，不能把它当作普通空字符串。
6. `compatibilityId` 仅在确认需要兼容已有 V1 库时填写；普通新建保留 `""`，不从新作者或新 ID 自动生成。V1 转 V2 的兼容迁移中，能从 `.mpext` 或 V1 `author`/原始 `id` 证明时必须填写预期的小写旧身份；身份无法证明时停止，不猜值。

## 当前精确字段集

`required_fields` 是每次转换都必须出现的固定集合；`optional_fields` 是允许出现、但必须有证据且非空的集合。检查器会拒绝白名单之外的字段并检查 JSON 类型。

### UPLOAD

必需字段：

```text
id, version, name, description, author, compatibilityId, cover,
isDevice, sku, main, mode, libraryConfig, meta
```

允许的附加字段：

```text
supportDevices, supportArch
```

固定值是 `mode: "upload"`、`isDevice: false`、`main: "main.js"`。没有外部全局 Arduino 库时
`libraryConfig` 为 `[]`；本地复制到 `public/libraries/` 的库不能因此加入该数组。`supportArch`
出现时会覆盖 `supportDevices`，两者的选择必须来自 V1 的板卡证据。

### PYTHON_BLOCK

必需且唯一的顶层字段集：

```text
id, version, name, description, author, compatibilityId, cover,
isDevice, sku, main, mode, meta
```

固定值是 `mode: "python-block"`、`isDevice: false`、`main: "main.js"`。Python 依赖不进入
`config.json`，只按 Python Reference 中的两个权威 V1 来源生成 `public/requirements.txt`；因此
`libraryConfig`、`supportDevices`、`supportArch` 都不能添加。

## 值的来源顺序

以下旧身份来源规则适用于 CONVERT；CREATE 使用已冻结规格，作者按 [author-identity.md](author-identity.md) 选定和规范化。UPGRADE 保留已有作者，除非本次明确要求修改署名。

`id` 使用规范化后的 V2 小写字母数字 ID；`compatibilityId` 使用旧包身份；`author`、`version`、
`name`、`description` 和 `sku` 只使用 V1 文件或已记录的用户证据；`cover` 指向目标 `public/`
中的实际封面；`meta.runtimeVersion` 只使用已加载 Topic 明确给出的 Runtime 最低版本。来源缺失的
字符串写 `""`，身份、入口或模式固定值无法满足时进入敏感节点，不以空值掩盖问题。

在新 Builder 根目录上先运行 `scripts/switch/create_config_skeleton.py` 生成固定字段骨架，再补充有证据
的值；不要直接手写一份脱离 profile 的配置。生成后必须运行
`scripts/switch/check_converted_extension.py`。字段不匹配、类型不匹配、固定值不匹配或 V1 字段泄漏都在
`npm run build` 前阻断。
