# UPLOAD：Arduino 上传模式

仅在路由结果为 `UPLOAD` 时读取。输入必须有根 `config.json` 和 `arduinoC/main.ts`；目标是 `extension/public/config.json` 的 `mode: "upload"`。不处理 Python、MicroPython、实时模式、主控扩展或完整审核。

## 生成资料入口

以 `select_reference_topics.py` 的 `PASS` 输出为唯一生成资料清单。该脚本根据 V1 inventory
自动合并 `route_profiles.UPLOAD.always` 与命中的菜单、Field、Runtime、Generator 和引脚
Topic，并逐项复核模式、路径和 SHA-256；不得绕过脚本一次读完全部生成资料。

生成资料说明当前 Wiki 支持的字段、API 和结构；本文件与 `shared-v2-patterns.md` 说明如何
保持 V1 语义。两者冲突时记录 Topic、当前规则和 V1 证据，进入敏感节点，不按样例或模型
知识自行裁决。

## 样例边界

- 基础样式参考：`ext2-SU03T01`、`ext2-SU03T02`、`ext2-SU03T02V2`。
- 条件样式参考：`ext2-BMP58X`，用于单积木 board 条件、动态引脚菜单、`supportArch`、REPORTER 和复杂库资源。
- `ext2-LegoDuinoPro`/YFROBOT 样例是不规范排除项，不得作为模板或字段来源。

## 盘点清单

读取并记录：根 `config.json`；`arduinoC/main.ts`；`_locales/`、`_menus/`、`_images/`；`libraries/`；`.mpext`、README、示例和截图（存在时）。对每个 block/function 记录 namespace、opcode/function、类型、文本、参数、shadow/default/range、菜单显示和值、board/boards 条件、include/object/setup/function、生成代码和资源依赖。

## 目标映射

目标通常包含：

```text
extension/
├── public/config.json
├── public/cover.*
├── public/icon/ 或 icon/
├── public/locales/ 或 locales/
├── public/libraries/<library>/
├── index.js
└── func.js
```

先按 [config-schema.md](config-schema.md) 的 `UPLOAD` profile 生成配置：顶层字段只能来自白名单，必需字段不能缺失，V1 的 `email`、`license`、`isBoard`、`platform`、`asset` 不得泄漏。新 V2 `id` 与旧 `compatibilityId` 按共享规则分别生成，保留可验证的 `author` 和语言文本；`mode` 固定 `upload`，样例扩展 `isDevice` 为 `false`，`main` 使用当前 Builder 入口。`sku` 和 `meta.runtimeVersion` 没有证据时写 `""`；`libraryConfig` 无外部全局 Arduino 库时写 `[]`。`supportDevices`、`supportArch` 只有证据支持时出现，不要用空结构占位。禁止添加 `boardConfig`。

`supportDevices` 表示整体设备范围；单积木 `board/boards` 条件表示可见性条件，二者不能互相替代。只有旧积木确实需要当前设备引脚时才使用 `getBoardPinsByType` 或设备 Runtime；BMP58X 动态 RX/TX 菜单属于条件样式，普通固定字符串/数字参数不能主动套用。

## index.js / func.js

- `index.js` 按当前 Builder 引入 `ArgumentType`、`BlockType`、图标、`Func` 和 locales，实现 `setLocale`、`getCodePrimitives`、`getInfo`。
- block 的 opcode、类型、text、arguments、menu、defaultValue、outputTypes 必须逐行对应语义矩阵。扩展名、积木和菜单显示文字均用 `formatMessage`，并在 `en.json`/`zh-cn.json` 中保持 key 对齐；动态菜单可采用 `menuText` + `buildMenuItems` 样式。
- V1 enum 通常变成 V2 menu；分别保留显示文字、实际 value 和默认值。
- `func.js` 方法使用当前签名：`functionName(generator, block, parameter)`；参数从 `parameter.NAME.code` 读取。
- V1 namespace 或兼容前缀不写入函数名。旧 opcode `winster-maxbot_driver-thirdex.speed` 在 V2
  必须对应 `blocks[].opcode: 'speed'` 与 `func.js` 的 `speed(...)`。
- `addInclude`、`addObject`、`addVariable`、`addSetup`、`addFunction` 各自只放对应职责。不要机械复制 V1 的 `addObject` 参数形态或 `PROGMEM`。
- COMMAND 返回语句；REPORTER/BOOLEAN 按当前 Builder 优先级返回 `[code, priority]`。普通 STRING 不自动添加 `symbol/menu`。

## 颜色与图标

- `color1`、`color2`、`color3` 必须存在且不能全部相同；优先使用 V1 `//% color="#xxxxxx"` 作为
  `color1`。
- 从 V1 `arduinoC/_images/icon.svg` 复制为 `blockIcon.svg`；复制一份后重新着色为 `menuIcon.svg`。
  `menuIcon.svg` 的 SVG 主色必须包含 `color1`，不能与 `blockIcon.svg` 原样相同。转换扫描会在构建前
  检查这两项。

## 库与停止条件

V1 自带 Arduino 库复制到 `public/libraries/<library>/`，保留实际需要的源码和 `library.properties`；外部全局库才进入 `libraryConfig`。版本不明、关键资源缺失、板卡无法映射、冲突未裁决或必须改变旧语义时停止并写敏感节点。

