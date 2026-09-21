# Basic：产物完成后的发布前审查

Basic 是产物完成后、发布前的标准审查。创建、转换、升级完成后进入 `REVIEW_EXISTING`；单独发布也先经过此阶段。复用同一源码、同一 ZIP 和相同环境的有效证据，不为了流程名重复构建。审查不修改扩展源码；经授权的构建与检查可生成产物和证据。源码修复后重查受影响项。

## 必需检查

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

## 观察类检查的默认程序与取证顺序

`blocks_visible` / `blocks_functional` 按“先判环境、再取证”执行，不做无程序的即兴尝试：

1. **先判环境**：Mind+ 是否已安装且本次可操作。不可用（或用户明确不配合观察）时，立即把两项记 `NOT_RUN`／`BLOCKED` 并注明原因，按终态交接用户；不要在等待观察的情况下继续组装其余证据。
2. **Mind+ 可用时的最小程序**：打开 Mind+ 并加载被审扩展（开发者模式扩展面板左下角「加载测试扩展」选择 `build/<id>@<version>/config.json`，或导入构建 ZIP）→ 新建工程 → 拖入或生成全部积木 → 截图存证 → 用代表性组合（命令接主程序、报告器接变量赋值）生成代码或运行，记录输入、预期与实际。
3. **证据绑定**：截图与工程导出存入运行 `evidence/`，`artifact_sha256` 绑定本次 ZIP；GUI 观察以用户确认或可审计观察记录为准。

构建产物复用：`build/` 目录与本轮源码摘要一致、且本源码上已记录过一次退出码 0 的构建时，`builder_build` 可复用该产物与既有日志，不重跑 webpack；源码或环境变化后必须重新构建。

安全审查在执行 npm 生命周期脚本或加载扩展前先进行一次：重点追踪外部命令、动态执行／解码载荷、网络发送目的、凭据读取、文件删除／越界写入、持久化、安装钩子和来源不明依赖。网络、串口、文件操作可能是合法功能，不能仅凭关键词判恶意；结合需求、数据流和用户授权判断。构建后补查 ZIP 内产物与依赖，未解释风险不得 PASS。不要执行疑似恶意代码来“验证”它。审查结果只代表已记录的范围，不保证绝对无恶意代码。

P1/P2 继续按 [issue-levels.md](issue-levels.md) 提醒，不把颜色、排版建议升级为阻断条件。八项必需检查、大小限制和授权／秘密／目标门槛不能降为 P1/P2。

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

对表中前七项分别填写 `result`、`method`、覆盖范围 `summary` 和带 SHA256 的证据文件列表。`builder_build`、`blocks_visible`、`blocks_functional` 都要填写 `artifact_sha256` 绑定实际测过的 ZIP。不能将未运行的检查填 PASS；`package_size` 由脚本生成。ZIP 不存在、超过上限、内容损坏、证据缺失／被修改或源码变化均阻断。

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
