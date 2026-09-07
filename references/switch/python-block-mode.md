# PYTHON_BLOCK：Python 积木模式

仅在路由结果为 `PYTHON_BLOCK` 时读取。输入必须有根 `config.json` 和 `python/main.ts`；目标是 `extension/public/config.json` 的 `mode: "python-block"`。不处理 MicroPython、实时模式、纯 Python 包迁移、主控扩展或完整审核。

## 生成资料入口

以 `select_reference_topics.py` 的 `PASS` 输出为唯一生成资料清单。脚本根据 V1 inventory
自动合并 `route_profiles.PYTHON_BLOCK.always` 与命中的依赖、本地库、菜单、Field 和 Python
Generator Topic，并逐项复核模式、路径和 SHA-256；不得自行搜索整包资料或跳过 Topic。

生成 Topic 说明当前 Wiki 支持的结构、字段和 API；本文件与 `shared-v2-patterns.md` 规定
V1 语义迁移。两者冲突时记录 Topic、V1 证据和影响，进入敏感节点。

## 盘点清单

读取并记录：根 `config.json`；`python/main.ts`；`_menus/`、`_locales/`、`_images/`；`libraries/**/*.py`；
`python/libraries/requirements.txt`（若存在）；README、`.mpext`、截图和打包行为（存在时）。语义矩阵至少
覆盖函数、可见积木、菜单、参数/default/shadow、生成 Python、local library、pip dependency 和前置关系。
其中依赖的唯一权威来源是 `config.json` 的 `asset.python.dependencies` 与
`python/libraries/requirements.txt`；README、源码 import、截图和打包行为只能作为其他语义证据，不能改变依赖清单。

## config 与结构

先按 [config-schema.md](config-schema.md) 的 `PYTHON_BLOCK` profile 生成配置：顶层字段必须完全属于该 profile，必需字段全部出现；新 V2 `id` 与旧 `compatibilityId` 按共享规则分别生成，`author`、名称、描述和封面按证据保真。`sku` 和 `meta.runtimeVersion` 没有证据时写 `""`。不得机械复制 V1 的 `platform`、`asset`、`email` 或 `license`，也不得添加 upload 专用的 `libraryConfig`、`supportDevices` 或 `supportArch`。

目标形态通常为：

```text
extension/
├── public/config.json
├── public/cover.*
├── public/requirements.txt       # 仅有外部 pip 依赖时
├── public/libraries/<source>.py  # 仅有本地库时
├── index.js
└── func.js
```

## index.js / func.js

- `index.js` 使用当前 Builder 的 `ArgumentType`、`BlockType`、图标、Func、translation 和 locales；`getCodePrimitives()` 返回 Func 实例。
- 每个 opcode、blockType、参数 key/order、menu text/value/default 和 output type 必须来自语义矩阵。扩展名、积木和菜单显示文字均用 `formatMessage`，并在 `en.json`/`zh-cn.json` 中保持 key 对齐；动态菜单可采用 `menuText` + `buildMenuItems` 样式。
- 普通 STRING 可以只有 `type` 和 `defaultValue`；V1 `shadow="normal"` 不显示引号，`shadow="string"` 按共享规则添加 `inputParams.symbol: '""'`。菜单配置仍需独立证据。
- V1 menu 的显示文字与实际值分别映射，不能按序号重编码。
- `func.js` 使用 `method(generator, block, parameter)`；参数从 `parameter.NAME.code` 读取。
- V1 namespace 不属于 Python 方法名：例如旧的 `winster-maxbot_driver-thirdex.speed` 只映射为
  `speed(...)`，不能写成 `Func.prototype['Maxbot.speed']`。方法名必须与 `index.js` 中的短 `opcode`
  一致。
- Python 积木函数必须返回要插入的 Python 代码；禁止使用上传模式的 `generator.addCode(...)` 代替
  `return code`。没有返回代码的 COMMAND 即使 Webpack 通过，也视为转换失败。
- `addImport` 保留真实 import；旧 `addDeclaration` 按其“全局变量/对象”行为迁移到当前 `addVariable`；初始化使用 `addInit`。当前位置语句由函数直接 `return code`，表达式按当前优先级返回 `[code, priority]`。V1 若按参数分支追加多段代码，应在当前函数中选择并拼接片段后统一返回；错误分支可使用 Wiki 已记录的 `generator.addErrorPrompt`。不得保留旧全局 `Generator` 调用，也不得引入生成 Topic 未记录的 API。
- inventory 报告 `MALFORMED_BLOCK_TYPE` 时，先从该函数的实际生成结果分类：只生成赋值、调用、打印等语句且不产生值时使用 `COMMAND`；返回单个值的表达式才进入 `REPORTER/BOOLEAN` 判断。只有分类唯一且不与菜单、打包行为或截图冲突时，`AUTO` 才可记录修正后继续；否则暂停审核。

## 依赖与资源

- V1 自带 `.py` 文件逐项复制到 `public/libraries/`，保留相对 import，复制前后核对 SHA-256；不要复制 `__pycache__`、模型缓存、虚拟环境或 `libraries.zip`。
- 依赖只从两个 V1 权威源读取：根 `config.json` 的 `asset.python.dependencies`，以及精确路径
  `python/libraries/requirements.txt`。不得从源码 import、README、截图、`.mpext` 或模型知识推导依赖。
- 按 `config.json` 中的声明顺序逐项保留依赖：值为空时写成不带版本约束的包名；值为纯版本号时写成
  `name==version`；已经带比较符或范围的值原样拼接。不得省略空版本项、改选最新版或判断某个包是平台内置。
- `python/libraries/requirements.txt` 存在时按原文件顺序读取并保留其中的 requirement 行；不要重排、升级、
  过滤或用源码 import 补行。配置声明与该文件同时出现时，分别记录两份原始证据；同一包的规格冲突时进入敏感节点，
  不自动合并或选择一方。
- V2 的 `public/requirements.txt` 只由上述两个来源产生：先放 config 声明转换出的行，再按原顺序放
  `python/libraries/requirements.txt` 的行；完全相同的重复行可以去重，但不同规格不能静默覆盖。两个来源都没有有效行时不创建文件。
- 转换扫描器会按 V1 盘点器生成的 `expected_requirement_lines` 对比 V2 文件；出现缺失、额外、重排或规格变化时，
  在 build 前阻断。
- 转换阶段不安装 requirements、不运行真实推理；这些属于独立审核。
- 缺少封面、图标、库源码、依赖版本或生成器 API 证据时停止，不生成替代内容。
