# Basic：产物完成后的发布前审查

Basic 是产物完成后、发布前的标准审查。创建、转换、升级完成后进入 `REVIEW_EXISTING`；单独发布也先经过此阶段。复用同一源码、同一 ZIP 和相同环境的有效证据，不为了流程名重复构建。审查不修改扩展源码；经授权的构建与检查可生成产物和证据。源码修复后重查受影响项。

## 必需检查

发现 P0 不停止审核，也不要求先修复再检查其余项；继续完成本次范围内所有可执行检查，最后统一报告各项结果、全部 P0/P1/P2 问题及其位置、影响和证据。前置失败或安全风险导致某项无法执行时，仅将该项记为 NOT_RUN／BLOCKED 并注明原因，继续其余独立检查，最终一并说明未验证项。P0 仍阻止 Basic 通过和发布；不得执行疑似恶意代码来补齐检查。

| 检查 ID | 通过依据 |
| --- | --- |
| `config_schema` | 当前模式配置字段、类型、必需资源符合契约 |
| `extension_static_integrity` | 入口、资源、依赖、翻译和积木到生成器的映射完整 |
| `source_semantics` | 代表性及风险功能与需求、原库一致，说明覆盖范围 |
| `malicious_code_review` | 人工／代理实际审查源码、构建脚本、依赖变动和构建产物；无未解释的危险行为 |
| `builder_build` | 实际构建命令退出码 0，产物来自当前源码，记录工具版本和命令日志 |
| `blocks_visible` | 对本次产物观察正常积木和二级菜单，参数、文字、图标与布局可用 |
| `blocks_functional` | 代表性积木及改动功能实际生成预期代码／执行预期运行时行为，记录输入、预期和实际结果 |
| `package_size` | 最终扩展 ZIP 大小 **≤ 5,000,000 字节**，包含 main.js 和 config.json；由脚本核验 |

构建通过不能替代积木显示／行为验证；静态阅读不能写成实际运行。可使用可用的本地测试环境或 Mind+ 人工观察，不声称验证真实硬件。记录环境、方法与实际覆盖范围；GUI 观察使用用户确认或实际可审计的观察记录。无法构建或观察时记录 NOT_RUN／BLOCKED，保留产物但不发布。已确认的源码编译错误为 P0；环境缺失单列“未验证”。

问题统一按 [issue-levels.md](issue-levels.md) 的 P0↔T0、P1↔T1、P2↔T2 判定。`source_semantics` 与 `blocks_functional` 的接入门槛不因不阻断编译使用的 P1 或待实物验证的 P2 疑点自动 FAIL；列出已完成的显示、参数／连接、实际代码与目标编译证据，将内部逻辑提醒和实物边界单列。必需的线上／本地检查未执行仍为 BLOCKED／NOT_RUN，不能用低等级掩盖缺项，也不能把未实测物理行为写成 PASS。

## 最小验证与取证顺序

先复用有效的开发阶段证据，再补缺项；不把八个检查 ID 当作八套独立测试或八份独立文件。

1. **先判环境**：确认 Mind+ 或已有本地验证环境能实际观察本次扩展。环境不可用或用户不配合观察时，两项观察记 `NOT_RUN`／`BLOCKED`，完成可达的源码检查后交接；不反复启动、安装替代环境、重试构建或拼出必然被拒的完整 Basic 报告。缺少观察仍禁止发布。
2. **最小观察**：加载被审扩展（Mind+ 开发者面板「加载测试扩展」选择 `build/<id>@<version>/config.json`，或导入构建 ZIP），观察积木面板和二级菜单的文字、参数、图标与布局；无需逐个拖出全部积木。用一个最小工程覆盖代表性组合、新增／改动路径和实际风险边界（如命令接主程序、报告器接变量赋值），生成代码或运行，记录输入、预期和实际。仅在发现异常或验收明确要求时扩大覆盖，不枚举所有参数组合。
3. **最小证据**：保留实际截图／可审计观察记录和行为结果；同一工程或记录可同时支持显示与行为检查。工程导出仅在复现或验收需要时保留，不强制截图与导出两套材料。证据存入运行 `evidence/`，`artifact_sha256` 绑定实际验证的 ZIP；不能用构建日志冒充观察。

构建产物复用：`build/` 与本轮源码摘要一致，且已有退出码 0 的构建日志时，复用产物与日志，不重跑 webpack。源码或构建环境变化后重新构建；新 ZIP 必须更新大小、摘要及其实际观察证据，只重查受影响行为，不重做无关测试。同一最终产物的一次验证可同时用于开发交接和 Basic。

安全审查在执行 npm 生命周期脚本或加载扩展前先进行一次：重点追踪外部命令、动态执行／解码载荷、网络发送目的、凭据读取、文件删除／越界写入、持久化、安装钩子和来源不明依赖。网络、串口、文件操作可能是合法功能，不能仅凭关键词判恶意；结合需求、数据流和用户授权判断。构建后补查 ZIP 内产物与依赖，未解释风险不得 PASS。不要执行疑似恶意代码来“验证”它。审查结果只代表已记录的范围，不保证绝对无恶意代码。

P1/P2 继续按 [issue-levels.md](issue-levels.md) 提醒，不把颜色、排版建议升级为阻断条件。按契约留空的必需字段（`compatibilityId`、`sku`、`meta.runtimeVersion` 等）是正确写法，不是缺陷，不列任何等级；“Empty compatibilityId”一类发现不要上报，`required_fields` 只校验字段是否存在、类型与固定值是否相符。八项必需检查、大小限制和授权／秘密／目标门槛不能降为 P1/P2。

Python 标准库和目标环境内置库无需额外 `requirements.txt` 声明；行空板 M10 内置的 `unihiker` 属于此类，不因未声明而列 P0/P1/P2。仅需额外安装的第三方库缺依赖声明时提醒 P1，不单凭缺声明阻断；运行时实际 import 错误按本次环境和错误证据另行判断。

在 upload 模式中，`supportArch: ["all"]` 是合法的全主板支持声明，不是空配置或非法架构；不得仅因使用 `"all"`、范围广或未枚举 `supportDevices` 报任何等级的问题，也不要求改成逐板列表。它存在时覆盖 `supportDevices`。功能审核仍按实际源码和代表性验证判断；发现具体主板不兼容时，报告对应缺陷及证据。

## 一份证据，贯穿发布

使用 `.mindplus-agent` 父运行的 `evidence/` 保存日志和报告，不能写进被哈希的项目源码。用 `scripts/hash_project.py` 获取当前源码摘要。最终 ZIP 保留在 Builder 的 build 目录或项目外，不把临时审核文件打包。

按 [公共 JSON 契约](contracts/basic-review.schema.json) 编写 `basic-evidence.json`，结构如下（示例中的摘要和路径必须替换为实际值）：

```json
{
  "schema_version": "mindplus.review-basic/v1",
  "project_root": "<项目绝对路径>",
  "project_sha256": "<源码 SHA256>",
  "artifact": {"path": "<最终扩展 ZIP 绝对路径>", "sha256": "<ZIP SHA256>"},
  "checks": {
    "builder_build": {
      "result": "PASS",
      "method": "npm run build；Node/npm 版本、工作目录及打包步骤见日志",
      "summary": "构建退出码为 0；ZIP 对应当前源码及此次构建",
      "exit_code": 0,
      "artifact_sha256": "<ZIP SHA256>",
      "evidence": [{"path": "<日志绝对路径>", "sha256": "<日志 SHA256>"}]
    }
  }
}
```

对表中前七项分别填写 `result`、`method`、覆盖范围 `summary` 和带 SHA256 的证据文件列表。同一份包含明确分项结果的报告可被多项引用，无需复制文件或重写同一结果。`builder_build`、`blocks_visible`、`blocks_functional` 都要填写 `artifact_sha256` 绑定实际测过的 ZIP。不能将未运行的检查填 PASS；`package_size` 由脚本生成。ZIP 不存在、超过上限、内容损坏、证据缺失／被修改或源码变化均阻断。

```text
python scripts/check_basic_review.py --project-root <project> --evidence <basic-evidence.json> --output <basic-review.json>
```

通过后，`mpa.py handoff` 使用 `REVIEWED_BASIC`，记录八个必需 PASS 检查，并加 `--artifact basic_review=<basic-review.json>`。每项 `--evidence <check_id>=<basic-review.json>` 可复用此报告。直接调用发布 preflight 时传 `--basic-review <basic-review.json>`，或传带此 artifact 的 Basic handoff。发布每个阶段重新验证源码、ZIP 和证据摘要；仅有静态检查的旧记录不能自动当成完整 Basic。

`mindplus.review-basic/v1` 是本流程的版本化证据契约。后续复用证据时核验契约版本、源码、ZIP 和环境，不因复用而放宽必需检查。

复用边界（避免重复劳动的两侧都写清）：

- `builder_build`、`blocks_visible`、`blocks_functional` 与 `package_size` 都绑定具体 ZIP 与源码摘要。四者同时不变时可原样复用；源码或产物任一变化，只需重跑受影响项，不必整轮重做。
- 终态的报告优先 `REPORTED_FINDINGS` handoff 会自动保留运行证据。其通过的静态检查（`config_schema`、`extension_static_integrity`、`source_semantics`、`malicious_code_review`）在确认项目摘要仍有效后可以复用；失败的静态门槛必须修复并重查。后续发布请求仍须补做构建、两项观察检查和包大小，并产出新的完整 `REVIEWED_BASIC` 报告。

## 证据骨架与交接示例（直接替换实际值）

校验器 fail-closed：`basic-evidence.json` 顶层必须自带 `"status": "PASS"`，八项检查缺一不可（`package_size` 由脚本生成，无需手写）。完整骨架：

```json
{
  "schema_version": "mindplus.review-basic/v1",
  "status": "PASS",
  "project_root": "<项目绝对路径>",
  "project_sha256": "<hash_project.py 输出>",
  "artifact": {"path": "<最终扩展 ZIP 绝对路径>", "sha256": "<ZIP SHA256>"},
  "checks": {
    "config_schema": {"result": "PASS", "method": "<方式>", "summary": "<覆盖范围>",
      "evidence": [{"path": "<绝对路径>", "sha256": "<文件 SHA256>"}]},
    "extension_static_integrity": {"result": "PASS", "method": "...", "summary": "...", "evidence": [{"path": "...", "sha256": "..."}]},
    "source_semantics": {"result": "PASS", "method": "...", "summary": "...", "evidence": [{"path": "...", "sha256": "..."}]},
    "malicious_code_review": {"result": "PASS", "method": "...", "summary": "...", "evidence": [{"path": "...", "sha256": "..."}]},
    "builder_build": {"result": "PASS", "method": "...", "summary": "...", "exit_code": 0,
      "artifact_sha256": "<与 artifact.sha256 相同>", "evidence": [{"path": "...", "sha256": "..."}]},
    "blocks_visible": {"result": "PASS", "method": "...", "summary": "...",
      "artifact_sha256": "<同上>", "evidence": [{"path": "...", "sha256": "..."}]},
    "blocks_functional": {"result": "PASS", "method": "...", "summary": "...",
      "artifact_sha256": "<同上>", "evidence": [{"path": "...", "sha256": "..."}]}
  }
}
```

校验与交接：

```text
python scripts/check_basic_review.py --project-root <项目> --evidence <basic-evidence.json> --output <basic-review.json>
python scripts/mpa.py handoff --work-root <work> --run-id <run> --workflow REVIEW_EXISTING --status PASS --outcome REVIEWED_BASIC --state TERMINAL --check config_schema=PASS --check extension_static_integrity=PASS --check source_semantics=PASS --check malicious_code_review=PASS --check builder_build=PASS --check blocks_visible=PASS --check blocks_functional=PASS --check package_size=PASS --evidence "<check_id>=<basic-review.json 绝对路径>"（每项一条） --artifact "basic_review=<basic-review.json 绝对路径>"
```

`--state` 可以省略：`handoff` 会按 `status`/`outcome` 推导（PASS 即 TERMINAL），显式写只是自证；`--evidence` 每项一条，缺项会被拒。校验器返回 `REVIEW.BASIC_NOT_READY` 时先看 `error` 文本：它区分「输入缺字段或字段非法」和「审核本身未通过」，前者补字段、后者才需要重跑检查。

后续需要复盘或复用完整 Basic 证据时，使用 `--keep-evidence` 保留运行记录与报告；`REPORTED_FINDINGS` 终态会自动保留其证据。其他未保留的成功运行会清理记录，清理后的路径不可继续核验。
# 测试场景有效性

动态审核先确认真实返回类型、初始化、作用域、板型和参数前提。字符串 reporter 接文本/字符串消费者；不得用数值等待槽通用承接所有 reporter。审核构造的不合理连接造成的失败记录为 INVALID_TEST，保留错误并修正场景，不计 P0，不否定合法用法已通过的证据。只有合法用法下确认的功能影响才按问题分级。报告须同时说明触发连接、输入值、实际代码/错误、正确用法及真实截图（缺图说明原因），不能仅在聊天解释。缺少动态证据仍如实 BLOCKED。

