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

后续需要复盘或复用证据时，使用 `--keep-evidence` 保留运行记录与报告；默认成功清理后的路径不可用于继续核验。
