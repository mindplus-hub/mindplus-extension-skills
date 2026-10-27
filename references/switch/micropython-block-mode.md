# MICROPYTHON：MicroPython 积木模式

用于 V2 创建、V1 自动转换、升级和审核，`config.mode` 为 `micropython-block`，新目录使用 `ext2-mpy-`。V1 默认入口为根 `config.json` 与 `micropython/main.ts`；声明了 `asset.micropython.dir/main` 时使用该实际源入口。不得把 MicroPython 源当成桌面 Python 积木源。

通过 `select_reference_topics.py --mode MICROPYTHON` 选择并校验 `micropython.*` 与共享主题，只读取返回的资料。

- 按 [config-schema.md](config-schema.md) 的独立 profile 写配置。`supportDevices` 必填且非空，设备 ID 使用 [device-ids.json](device-ids.json)。不添加上传模式的 `libraryConfig` 或 `supportArch`，也不套用上传 Runtime 0.0.2 的 15 板清单作为本模式的兼容范围。
- `index.js` 的 `getCodePrimitives()` 返回 Func；方法为 `opcode(generator, block, parameter)`，参数取 `parameter.NAME.code`。积木当前位置返回字符串或 `[code, priority]`；导入、变量、初始化和函数分别使用本模式生成器 API。
- `addWhile(id, code, isCover)` 从 Mind+ V2.0.8 起可用，用于在主循环头部插入代码；需要使用时确认目标 Mind+ 版本，普通积木仍返回当前位置代码。`getSetup`、`getStaticFunction` 可读取已有初始化／函数定义，不套用上传生成器签名。
- 本地 MicroPython 库放 `public/libraries/`；按已确认依赖保留可选 `public/requirements.txt`。MicroPython 的模块、固件内置库和依赖不能当作桌面 Python 的 pip 包推断安装。
- 双语文本、菜单、资源和 README 按共享规则处理；静态检查使用 `check_converted_extension.py --mode MICROPYTHON`，创建时输入由规格适配器生成的 inventory。

构建、Mind+ 中的积木显示、生成的 MicroPython 代码与真机运行分别记录。Builder 构建通过不能证明固件或依赖可用。

## V1 自动转换

1. 按 [转换流程](../workflows/switch.md) 运行盘点，选定 `MICROPYTHON`。使用 `v1_entry_inventory.MICROPYTHON` 的短函数名、标签与颜色，源目录保持只读。资源从所选入口所属目录的 `_images`、`_locales`、`_menus`、`libraries` 盘点，不硬编码到 python 或 arduinoC。
2. 把每个 V1 `export function opcode(parameter, block)` 转成同名 `opcode(generator, block, parameter)`，保留 blockType、参数 key/order/default、shadow、菜单实际值与板卡条件。空 tag 函数按共享 SUBMENU 规则处理。
3. V1 的 `Generator.addCode(code)` 改为在原积木位置 `return code`，报告器保留表达式与优先级；同一方法多次 addCode 按原执行顺序合并返回，不丢分支或事件回调。全局区 API 逐项按所选生成主题转换，尤其 `addImport`／`addFunction` 不能照搬 V1 的 id/code 参数数量。迁移 `addWhile` 时保留循环头部的执行位置，并确认目标 Mind+ 为 V2.0.8 及以上；不要将循环头部代码移到普通积木位置。
4. 只以 `micropython_dependency_inventory` 的 `config.json:asset.micropython.dependencies`、所选源目录 `libraries/requirements.txt` 为依赖依据，按 `expected_requirement_lines` 写目标文件。`local_libraries` 复制到 `public/libraries`，逐文件校验 SHA-256；不借用 `python_dependency_inventory`，不从 import 推断 pip 包或升级版本。
5. 从该模式的 source_asset 板卡声明与已验证设备映射填写必需的非空 `supportDevices`；旧 board 字符串不是 V2 设备 ID，也不提供 V2 设备版本。确有缺失时只补查对应设备证据，不因为模式本身阻断转换。兼容 ID 来自旧包身份，不能用清理后的新 ID 反推。
6. 本模式的代表性对照关注受影响的初始化顺序、循环位置、报告器表达式或回调。静态检查、源快照、资源校验、构建与 Basic 由共享转换流程各执行一次，本节不追加一轮。
