# V2 扩展编写惯例词典（conventions）

本文件是 CREATE 与 CONVERT 共享的惯例层：generated/ 里的 Wiki 事实回答"字段和 API 是什么"，
本文件回答"真实项目里大家怎么写"。每条惯例都带证据来源；没有证据的写法不要采用。
设备 ID、sku、supportArch 的机器可读字典见 [device-ids.json](device-ids.json)，
由 `scripts/switch/check_converted_extension.py` 强制校验。

## cover（扩展卡片封面）

制作或修改封面时按需读取 [cover-design.md](cover-design.md)。它是用户指定的展示约定，不改变 config 字段契约或发布门槛。

## sku（产品型号）

| 场景 | 写法 | 证据 |
| --- | --- | --- |
| 通信类/板卡类扩展，非 DFRobot SKU 产品 | `""` | ext2-espnow、ext2-ds1302 |
| 单一传感器模块 | `"SEN0237"` | ext2-sen0237、ext2-sen0691 |
| 同家族多型号共用一个扩展 | `"SEN0664\|SEN0665"`（管道符连接） | ext2-BMP58X |

格式约束：空串，或大写字母数字段以 `|` 连接。

## supportDevices 与 supportArch（设备范围）

- `supportDevices` 是对象：`{"dev-DFRobot-<board>": "^0.0.1", ...}`，键必须在
  [device-ids.json](device-ids.json) 字典内，值统一 `^0.0.1`（官方文档示例与全部已验证项目一致）。
- 二者表达整体设备范围；单积木的 `board/boards` 是可见性条件，不能互相替代
  （见 [upload-mode.md](upload-mode.md)）。
- 三种合法组合（按扩展类型选一种）：
  - **设备范围**：声明 supportDevices、省略 supportArch（espnow/ds1302/C4001）；
  - **全架构**：省略 supportDevices、写 `supportArch: ["all"]`（BMP58X）；
  - **架构族**（仅 upload 模式）：写 `supportArch: ["<platform>:<arch>"]`，架构取主板
    `boardConfig.board` 前两段如 `"arduino:avr"`（官方文档）。
- 官方语义：supportArch 与 supportDevices 同时设置时 **supportArch 覆盖** supportDevices；
  无证据不要同时写两者。
- 面向零基础用户选板：把字典里的**板名**（arduinoUno、unihikerK10…）列给用户选择，
  不要求用户知道设备 ID。目标板不在字典里时按 device-ids.json 的
  `unknown_device_recovery` 三条路径处理，绝不拼造 ID。

## author（作者）

CREATE 的作者来源与英文规范化见 [author-identity.md](author-identity.md)，在冻结规格前处理。CONVERT／UPGRADE 保留来源作者；不默认沿用模板的 DFRobot 或 MindPlus 作为新库作者。

## compatibilityId（旧包身份）

`config.compatibilityId` 只有确认需要兼容已有 V1 库时才填写，否则保留空字符串 `""`。字段名是 `compatibilityId`（大写 I），不是 `compatibilityld`。

- CREATE：`identity.compatibility_id` 默认空；省略或 null 也映射为空字符串。不要根据新建库的 author/id 自动拼接，也不要照抄模板值。确有旧库兼容需求时，记录用户要求及旧包身份来源后填写。
- CONVERT：一般需要兼容被转换的 V1 库，从旧 `.mpext` 文件名或 V1 author／原始 id 取得小写身份；通常形如 `<old-author>-<old-id>-thirdex`。不能用清理后的 V2 ID 替代原始 ID；按 generated 的 `shared.v1-compatibility` 主题处理。包可能放在源目录**内部**，也可能与源目录**并列**（`x-thirdex-V0.0.1/` 与 `x-thirdex-V0.0.1.mpext` 同级），两种都要认；只能按 author/id 派生时先小写、再把空白写成 `-`（旧身份不含空白）。
- UPGRADE：保留已有兼容关系，不因新署名或版本更新生成、替换或清空；只有本次明确要求变更兼容范围时才调整。
- 已确认兼容需求但旧身份无法证明时，继续核实来源，不编造值，也不以空字符串冒充完成兼容。

## meta.runtimeVersion（Runtime 最低版本）

| 取值 | 适用 | 证据 |
| --- | --- | --- |
| `"0.0.1"` | 不使用设备 Runtime / 板卡引脚 API | ext2-sen0237、ext2-espnow |
| `"0.0.2"` | 使用 `getBoardPinsByType` 等板卡引脚 Runtime API | ext2-BMP58X、ext2-ds1302（均 0.0.2 且使用板卡引脚） |

没有 Runtime API 证据时写 `""`（[config-schema.md](config-schema.md) 的 missing_value_policy）。

## 语料自包含边界（CREATE 与 CONVERT 同规）

本 Skill 面向从未做过扩展开发的用户，**不假设用户机器上存在任何示例项目或参考库**。
编写扩展所需的全部知识来自 Skill 内置语料：generated/ 的官方 Wiki 事实、本词典、
[block-organization.md](block-organization.md)、shared-v2-patterns 与各模式文档；
内置语料有缺口时按 [official-corpus.md](official-corpus.md) 检索官方 Gitee 组织仓库。

1. 内置语料优先且通常足够；能用词典回答的问题不转引任何外部项目。
2. 用户**主动提供**的示例项目/旧扩展可以作为 C2 证据参考（例如"参考这个 C4001 的组织方式"），
   此时采用的每条惯例必须在 run log / spec 里记录来源路径；未提供的不要去找、不要假设存在。
3. 内置语料缺口的第一回退：按 official-corpus.md 协议检索官方组织
   `gitee.com/mind-plus`（只读、带 provenance 存证，官方发布行为按 C2 记录）。
   学到的可复用惯例（如新设备 ID）作为词典更新提案回填，运行中不改词典。
4. 内置语料与官方仓库都不覆盖、用户也未提供参考时，停止为 `REFERENCE.UNSUPPORTED_TOPIC`，
   并把缺口转成一个具体的、零基础用户能回答的问题（例如"你的扩展需要限定哪些主控板？
   以下是内置清单…"），不得推断。
5. 新增设备 ID 或新惯例的唯一途径：带着证据（官方文档链接、官方仓库 provenance 或
   已验证项目）更新 device-ids.json / 本文件，再使用。
