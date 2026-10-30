# V1 → V2 共享标准

## 证据优先级

`C3` 环境事实、脚本输出、明确文件字段 > `C2` 打包行为、截图、可见积木、Builder 示例 > `C1` 已校验资料和旧文档 > `C0` 模型知识或类比。高等级证据冲突时暂停，不按多数票猜测。

## 共享语料边界

`references/switch/` 是 CREATE 与 CONVERT 共用且**自包含**的语料库：面向零基础用户，
不假设机器上存在示例项目。设备 ID、sku、compatibilityId、runtimeVersion 等真实项目惯例以
[conventions.md](conventions.md) 与 [device-ids.json](device-ids.json) 为准（device-ids 由静态检查器强制）。
用户主动提供的示例项目可作 C2 证据并须记录来源；语料不覆盖且用户未提供参考时停止为
`REFERENCE.UNSUPPORTED_TOPIC` 并提出具体问题，完整规则见 conventions.md 的"语料自包含边界"。

## 保真规则

- 默认保留 V1 的 opcode/function、参数 key/order/default、菜单实际 value、积木类型、资源和生成代码行为。
- 每个可见积木、菜单、依赖、库和资源都进入语义矩阵；注释掉的 helper 不自动暴露为积木。
- 普通 `ArgumentType.STRING` 不因为类型名称自动添加 `symbol`、`menu` 或 `inputParams`。
- V1 的 `shadow="normal"` 与 `shadow="string"` 不能合并为相同显示行为；按下方映射保留引号。
- V1 自带源码库与外部依赖分开：源码库复制到模式规定的 `public/libraries/`。Python 外部依赖只从
  V1 根 `config.json` 的 `asset.python.dependencies` 和 `python/libraries/requirements.txt` 读取；
  源码 import、README、截图和模型知识不能补充、删除或改写依赖。
- V1 与 V2 的 Generator 调用形态不同，不能照抄实参：最典型的是 `addInclude`——V1 第二个参数是
  整条 `#include ...` 指令，V2 要的是**裸头文件名**（详见 [upload-mode.md](upload-mode.md)）。
  与之同类，V1 的 `addObject`、`PROGMEM` 写法也不机械迁移。
- 缺失封面、图标、库或必要 API 的源证据时停止，不生成占位内容、不选最新版。依赖版本为空时保留
  这个源事实，不自行判断为平台内置或替换成最新版。

## V1 shadow 输入框与 V2 引号显示

V1 注解中 `.defl="..."` 外层引号是注解语法，不是默认值本身携带的引号：

```typescript
//% NM.shadow="normal" NM.defl="obj"
//% SS.shadow="string" SS.defl="mind+"
```

- `normal`：输入框不显示引号，V2 使用 `type: ArgumentType.STRING, defaultValue: "obj"`，不添加引号 `symbol`。
- `string`：输入框显示引号，V2 使用 `type: ArgumentType.STRING, defaultValue: "mind+", inputParams: { symbol: '""' }`。对应所选 `shared.block.special` 的「3. 积木 field 符号显示」，`symbol` 放在 `inputParams` 内。
- 不把默认值改成含额外引号的 `defaultValue: '"mind+"'` 来模拟显示效果。
- `symbol` 是 field 显示配置，不凭它推断生成代码会自动带引号。继续对照 V1 生成器及 V2 `parameter.NAME.code` 的实际约定，保留标识符/表达式与字符串字面量的差异；不要再无条件包一层引号。

语义矩阵应记录 shadow 类型、默认值、field 引号显示、生成代码引号处理。此规则适用于 UPLOAD、PYTHON_BLOCK 和 MICROPYTHON；REALTIME 保留原有 arguments/defaultValue 与实际值。

## opcode 与生成函数映射

- V1 的 namespace、作者/id 兼容前缀和序列化 opcode 前缀只用于识别旧项目；它们不是 V2
  `func.js` 的方法名。V1 解包中形如 `"opcode": "winster-maxbot_driver-thirdex.speed"` 的值映射为 V2
  `index.js` 的 `opcode: 'speed'` 和 `func.js` 的 `speed(...)`。
- `func.js` 中禁止 `Maxbot.speed`、`Maxbot.stop`、`winster-maxbot_driver-thirdex.speed` 这类
  带 namespace 的方法名；方法名必须与 `blocks[].opcode` 和 V1 导出的短函数名逐项一致。
- Python 积木模式的函数必须返回当前积木生成的 Python 代码；不得把上传模式的
  `generator.addCode(...)` 机械搬入 Python `func.js`。`addImport`/`addInit` 等区域 API 与积木
  位置的 `return code` 分工按 Python Topic 执行。

## 颜色与图标规范

颜色和图标样式按 [issue-levels.md](../issue-levels.md) 列为 P1；缺少必需字段或资源导致加载失败才是 P0。下列样式目标不单独阻断构建或发布。

- `getInfo()` 必须提供 `color1`、`color2`、`color3`，不能三个值相同；有 V1 `//% color="#xxxxxx"`
  时，`color1` 优先采用该值。
- `blockIcon.svg` 从 V1 `arduinoC/_images/icon.svg` 复制并重命名，可保留原配色。
- `menuIcon.svg` 以同一图标为底稿但必须重新着色；其 SVG 中必须能确认主色与 `color1` 对齐，
  不能与 `blockIcon.svg` 原样相同。不能只通过构建成功推断颜色正确。

## 标识与资源

- V2 `id` 只允许字母数字。本转换默认生成小写字母数字 ID：删除 V1 `id` 中的符号并转小写；用户明确指定另一个小写字母数字 ID 时记录决定并传给扫描器。结果为空或与已存在目标冲突时暂停。该规范化只改变 V2 身份，不得改 opcode/function。
- `compatibilityId` 保留全小写旧加载身份，优先从 V1 根目录实际 `.mpext` 文件名去掉 `-V<版本>.mpext` 后取得；**包也可能与源目录并列**（`x-thirdex-V0.0.1/` 与 `x-thirdex-V0.0.1.mpext` 同级），这种情况按源目录名去掉版本号认领同级包，不要把解压目录名当证据、也不要漏看。没有包时才按 Wiki 的 `author-id-thirdex` 规则从原始 V1 `author`/`id` 派生：**先小写、再把空白写成 `-`**（旧身份不含空白，`id: ESP8266 IOT` 对应 `esp8266-iot`；下划线、中文、括号等原始字符保留）。多个包身份不一致或 config 与包身份冲突时暂停。不得用清理后的 V2 `id` 反推兼容 ID。
- 示例：V1 `id: Maxbot_driver` 生成 V2 `id: maxbotdriver`；旧包 `winster-maxbot_driver-thirdex-V0.0.2.mpext` 对应 `compatibilityId: winster-maxbot_driver-thirdex`；author `DJKJ` + `id: ESP8266 IOT` 的旧包名是 `djkj-esp8266-iot-thirdex-V0.0.1.mpext`（连字符，不是空格）。
- 不照抄样例的业务 id、author、版本、颜色、设备、引脚、opcode、菜单值或依赖。
- 优先复用 V1 封面和图标；`config.cover` 必须指向目标 `public/` 中实际存在的文件。未要求制作时不自行重画；新建或已授权制作／替换的封面按 [cover-design.md](cover-design.md)，其余图标和截图仍遵循原有来源规则。
- 复制文件后记录源/目标相对路径、大小和 SHA-256。

## `config.json` 字段契约

- 生成前读取 [`config-schema.md`](config-schema.md)；它是四种 V2 模式的顶层字段白名单和必需字段清单；V1 自动转换覆盖四种模式的已注册入口。V1 `email`、`license`、`isBoard`、`platform`、`asset` 不得进入 V2 配置。
- 字符串元数据没有可验证描述时写 `""`。`meta.runtimeVersion` 写扩展实际依赖的 runtime API 最低版本：只用 `0.0.1` 能力（`setLocale`/`getCodePrimitives`/`getInfo`、`Generator.*`）就写 `"0.0.1"`，只有用到 `getBoardPinsByType` 这类 `0.0.2` API 才写 `"0.0.2"`；写成 `""` 只表示依赖版本无法确定，不是省事的默认值。`libraryConfig` 等必需数组使用 schema 的空数组默认值；`supportDevices`、`supportArch` 是设备范围声明，UPLOAD 至少给出一个非空项，不能写空结构，也不能因为未使用引脚 API 就一并省略。
- `config.json` 的严格字段、JSON 类型和固定值检查必须在唯一一次 Builder build 之前完成；检查失败时先修正或记录敏感节点，不用构建成功掩盖配置错误。

## 二级菜单

遇到 V1 `blockType="tag"` 二级标签文字时，按 [标签到二级菜单映射](v1-secondary-labels.md) 转换；空标签函数不生成真实功能积木。

## 翻译门禁

- 扫描 V1 `_locales/`、`_menus/`、入口文件和双语 config；“V1 没有完整 locales”不等于“没有可迁移翻译证据”。
- 扩展名、所有积木 `text`、静态和动态菜单显示文字都必须使用 `formatMessage`；菜单实际 `value` 与顺序保持不变。
- **`formatMessage` 必须在 `getInfo()` 调用期间解析**：把结果存进模块顶层常量（或任何在 `import` 时就求值的结构）会在 locale 仍为默认值时被冻结，之后切换语言只更新积木文字，**下拉菜单文字保持默认语言**。菜单项要写成函数、在 `getInfo()` 里调用（`menus: { xMenu: menu(xItems()) }`），或把 `{id, default}` 消息对象作为 `text` 交给运行时解析。该缺陷用静态检查看不出来（message ID 齐全、`FORMAT_MESSAGE_ID_MISSING` 也不会报），只能在目标语言下实际读取 `getInfo()` 的输出验证。
- 翻译 ID 使用稳定的 V2 命名空间，不沿用包含旧非法字符或旧大小写的 V1 `id`。`en.json` 与 `zh-cn.json` 的 key 集必须一致，并覆盖 index.js 中的所有静态 message ID。
- V1 英文默认文本与中文 locale 可组合成两套目标资源；确实缺少某语言且无法从 config/默认文本证明时进入敏感节点，不直接留下裸字符串，也不编造翻译。

## 硬边界

`boardConfig` 不是 V2 扩展 `public/config.json` 顶层字段；不要因为旧说明或模型知识添加未在当前资料/Builder 中出现的字段。转换产物进入 Basic 检查构建、积木显示与代表性行为；上传和设备验收不属于本 Skill。
