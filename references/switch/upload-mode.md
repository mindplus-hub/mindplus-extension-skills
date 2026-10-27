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

V1 板型映射按实际设备身份核对，不能凭芯片名或名称相似直接对应 V2 ID。Mind+ V1 内置板型 `esp32` 指掌控板，应映射到 `dev-DFRobot-handpyEsp32`，不能映射到通用 `dev-DFRobot-Esp32`；`firebeetleesp32` / `firebeetleesp32e` 保持各自设备身份。板型身份存在歧义时先核对 V1 设备定义或用户确认，再填写 `supportDevices` 和最低版本，不扩大支持范围。

## 主板引脚菜单迁移

- V1 `_menus/<board>.json` 中用于选择当前主板物理引脚的菜单，应迁移为 `runtime.getBoardPinsByType()`；加载 `upload.pins` Topic，并将 `meta.runtimeVersion` 设为至少 `0.0.2`。不要把旧引脚表合并为自建 `pin-menus.json`，也不要以板型映射维护固定 GPIO 列表。普通枚举、模块内部通道及协议值仍按原菜单迁移。
- 使用 runtime `0.0.2` 引脚 API 时，必须同时核对 `upload.config` Topic 中 `supportDevices` 的各主板最低版本；不能只提高 `meta.runtimeVersion` 而保留旧主板版本。未列入该 runtime 适配范围的主板不得凭旧声明保留；同步更新 README 支持表，并记录兼容范围变化。
- 根据底层库实际用途选择能力：硬件串口使用 `UART_TX` / `UART_RX`。经典 Uno/Nano（ATmega328P）的 AVR `SoftwareSerial` 使用引脚变化中断（PCINT）接收，TX/RX 分别使用 `DIGITAL_WRITE` / `DIGITAL_READ`；不能用仅表示外部中断的 `EXT_INTERRUPT` 将 RX 错限为 D2/D3。该处理不能推广到 Mega、Leonardo 等板型，须核对实际串口库和主板 PCINT 能力后再筛选；只有库确实依赖外部中断时才使用 `EXT_INTERRUPT`。同一库按平台切换串口实现时按实际实现选择能力，不只按 Tx/Rx 参数名判断。参考 [Arduino SoftwareSerial 说明](https://docs.arduino.cc/learn/built-in-libraries/software-serial)及[官方实现](https://github.com/arduino/ArduinoCore-avr/blob/master/libraries/SoftwareSerial/src/SoftwareSerial.cpp)。
- 在 `getInfo()` 中获取当前主板菜单，直接保留 runtime 返回的 `text` / `value`，不再翻译主板引脚或给值额外加引号。默认值必须来自返回列表；原默认引脚仍可用时可保留，否则选择有效项并记录默认值变化。空列表不得回退到旧固定引脚表。
- 仅验证受影响范围：菜单确实跟随 runtime 返回值变化、空列表不崩溃、默认值在菜单内，以及生成代码保留正确的引脚值和 RX/TX 参数顺序。构建或模拟 runtime 通过不等于原生显示、目标编译或硬件通过。

## index.js / func.js

- 源码保持可读的多行格式：类方法、积木对象、参数和菜单配置按层级展开并统一缩进，不将整个积木定义或多个方法挤成一行。压缩仅用于 Builder 的构建产物。
- `index.js` 按当前 Builder 引入 `ArgumentType`、`BlockType`、图标、`Func` 和 locales，实现 `setLocale`、`getCodePrimitives`、`getInfo`。
- block 的 opcode、类型、text、arguments、menu、defaultValue、outputTypes 必须逐行对应语义矩阵。扩展名、积木和菜单显示文字均用 `formatMessage`，并在 `en.json`/`zh-cn.json` 中保持 key 对齐；动态菜单可采用 `menuText` + `buildMenuItems` 样式。
- V1 enum 通常变成 V2 menu；分别保留显示文字、实际 value 和默认值。
- 菜单文字的 `formatMessage` 必须发生在 `getInfo()` 调用期间：菜单项写成函数、在 `getInfo()` 内调用（`menus: { xMenu: menu(xItems()) }`），不要做成模块顶层常量——那样在 `import` 时（locale 仍是默认值）就求值并冻结，切换语言后只有积木文字跟着变，**下拉框仍是默认语言**。判断方法：设置目标语言后读取 `getInfo()` 的 `menus`，确认 `items[].text` 已切换。
- `func.js` 方法使用当前签名：`functionName(generator, block, parameter)`；参数从 `parameter.NAME.code` 读取。
- V1 namespace 或兼容前缀不写入函数名。旧 opcode `winster-maxbot_driver-thirdex.speed` 在 V2
  必须对应 `blocks[].opcode: 'speed'` 与 `func.js` 的 `speed(...)`。
- `addInclude`、`addObject`、`addVariable`、`addSetup`、`addFunction` 各自只放对应职责。不要机械复制 V1 的 `addObject` 参数形态或 `PROGMEM`。
- `addInclude` 的实参只写**裸头文件名**，不写 `#include` 指令、尖括号或引号。运行时实现（upload-gui generator，2026-09-15 核对）就是一参 `addInclude('X.h')` → `#include <X.h>`、两参 `addInclude('键', 'X.h')` → `#include "X.h"`：两个实参都被**原样**塞进指令里，`id` 只多承担一个去重/覆盖键的作用。因此一参时 `id` 本身也不能带尖括号，两参时第二个参数是头文件名而不是整条指令。V1 的 `Generator.addInclude(id, '#include <X.h>')` 第二个参数是整条指令，照抄到 V2 会生成 `#include "#include <X.h>"`，编译必然失败；正确写法是丢掉 `#include`、尖括号和引号，只留 `X.h`。`check_converted_extension.py` 会检查 `func.js` 里的字符串字面量实参（计算得来的实参不判断）。注意生成的 `upload.generator.add-include` Topic 措辞会误导：它把 `code` 写成"实际生成代码"、把 `id` 举例成 `<MPython.h>`；按运行时实现，这两个实参都只能是**裸名字**，以本文件的说明为准。
- COMMAND 返回语句；REPORTER/BOOLEAN 按当前 Builder 优先级返回 `[code, priority]`。普通 STRING 不因类型名自动添加 `symbol/menu`；V1 `shadow="string"` 则按共享规则添加 `inputParams.symbol: '""'`，`shadow="normal"` 不显示引号。

## 颜色与图标

- `color1`、`color2`、`color3` 必须存在且不能全部相同；优先使用 V1 `//% color="#xxxxxx"` 作为
  `color1`。
- 从 V1 `arduinoC/_images/icon.svg` 复制为 `blockIcon.svg`；复制一份后重新着色为 `menuIcon.svg`。
  `menuIcon.svg` 的 SVG 主色必须包含 `color1`，不能与 `blockIcon.svg` 原样相同。转换扫描会在构建前
  检查这两项。

## 库与停止条件

V1 自带 Arduino 库复制到 `public/libraries/<library>/`，保留实际需要的源码和 `library.properties`；外部全局库才进入 `libraryConfig`。版本不明、关键资源缺失、板卡无法映射、冲突未裁决或必须改变旧语义时停止并写敏感节点。
