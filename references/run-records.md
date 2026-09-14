# 运行记录与证据链

新运行统一写入工作目录下的 `.mindplus-agent`，项目源码仍在外部项目目录。父流程与转换子流程使用同一个 parent_run_id；命令返回的 run_root 是该命令负责的记录目录，不能混用。

```text
.mindplus-agent/
├── runs/<parent_run_id>/
│   ├── request.json             # 冻结的目标、路径和授权
│   ├── route.json               # 路由决定
│   ├── run.json                 # 当前流程和状态
│   ├── extension-spec.json      # 新建规格（或 request 指定的外部规格）
│   ├── upgrade-baseline.json    # 升级前基线，仅升级使用
│   ├── children/CONVERT_FRESH/
│   │   ├── record.json          # 父 ID、来源、目标、模式和策略绑定
│   │   ├── log.md               # S-1 至 S11 检查点与操作记录
│   │   └── record/              # 来源清单、脚手架版本、扫描与构建证据
│   ├── evidence/               # 父流程检查及发布证据
│   └── handoffs/<workflow>.json # 检查结果、原始证据路径、输入与项目哈希
└── conversions/<run_id>/       # 没有父任务的独立转换；同样含 record.json/log.md/record
```

## 分析顺序

1. 从 request 和 route 确认本次目标及范围，再看 run 的当前状态。
2. 转换时核对 record.json 的来源、目标与父请求一致；log.md 用于定位中断步骤，record 中的原始输出用于判断发生了什么。重复初始化不新建随机子任务、不清零安装或构建计数。
3. 从 handoff 的 checks 追到各 evidence 文件，区分 P0、P1/P2 和 NOT_RUN；转换 handoff 自动附带绑定文件及日志的路径和 SHA-256。日志不是构建结果的替代证据。
4. 输入哈希证明使用了哪个来源，项目哈希证明检查了哪个输出；发布的提交和远端引用另行核验。它们不能互相替代，也不证明硬件已验收。

## 保留、恢复与旧记录

- 需要事后分析时，在父任务 start 使用 `--keep-evidence`，或在最终 transition 指定该选项。现有完成清理策略不变：未保留的成功父任务会连同其子记录清理；失败和等待任务保留。手动 `mpa.py clean` 会删除证据，分析前不要执行。
- 无父任务的独立转换收进 conversions；`clean --all` 同时识别独立转换与旧 `.ms`。运行中记录需按原有 force 规则处理。
- 历史 `.ms/<id>` 不自动移动或复制，避免破坏既有绝对路径及哈希。继续旧任务时沿用原日志与证据路径；父 handoff 可用 `--artifact legacy_conversion_log=<旧日志绝对路径>` 显式关联。新任务不再创建 `.ms`。
- `.mindplus-agent` 与旧 `.ms` 都从源码扫描、项目哈希和发布文件集合排除；不要在记录里保存令牌或私有源码全文。
