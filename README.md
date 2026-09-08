# MindPlus Agent Skill

本仓库是一份可整体安装的 Agent Skill，让 AI Agent 按统一流程完成 **Mind+ V2 扩展创建、V1 转换、基础审核和 Gitee 发布**

## 设计思路

```text
用户需求
   │
   ▼
识别目标与路径并路由执行
   ├─ 新建扩展 ── 创建 + 基础检查 ── 按需发布
   ├─ 转换 V1 ── 转换 + 基础检查 ── 按需发布
   ├─ 审核现有扩展 ── BASIC 只读审核
   └─ 发布现有项目 ── 发布前检查 ── 推送并核实远端

```

- **按需加载**：入口只负责路由，选中哪个流程才读取对应资料，避免一次加载全部说明。
- **脚本处理重复工作**：路由、哈希、结果交接、静态检查和发布步骤由脚本处理；扩展行为和代码实现由 Agent 根据需求与来源判断。
- **减少重复审核**：创建和转换已经包含基础检查，不自动追加独立审核。已有检查在内容、范围和环境仍适用时可以复用。
- **区分完成程度**：静态检查、构建、Mind+ 使用和硬件验证分别记录。推送成功不代表已在设备上验证。
- **支持中断恢复**：运行记录保存当前流程和结果，通过 `resume` 恢复；相同 run ID 不能被另一个请求覆盖。

## 支持的功能

| 功能 | 内容 |
| --- | --- |
| 创建 V2 扩展 | 从需求整理规格，准备固定版本的 Builder 脚手架，生成配置、积木、代码生成器、资源和说明 |
| V1 → V2 转换 | 分析一个 V1 扩展及所选模式，保留有依据的身份、参数、依赖和行为，转换到新的 V2 目录 |
| 基础检查 | 配置、资源引用、本地化、生成器映射、明显语义问题和项目说明等 |
| Gitee 发布 | 发布到已有仓库，或按授权创建仓库；检查文件集合、敏感信息、提交树、推送和远端引用 |
| 组合任务 | 创建后发布、转换后发布、审核后发布；只串联本次要求的步骤 |

Gitee 除 SSH 外创建仓库等操作仍需申请个人令牌作为本地凭据，可选择其一存放：

1. `GITEE_TOKEN` / `GITEE_ACCESS_TOKEN` 环境变量
2. 用户目录下的 `.gitee-token` 

不要将 token 放进聊天、仓库、URL 或命令参数，创建扩展本身不要求 Gitee token。

## 安装

### Codex

按当前官方文档，推荐使用以下位置，二选一即可：

| 范围 | 完整安装目录 |
| --- | --- |
| 用户级，跨项目使用 | `~/.agents/skills/mindplus-agent-skill/` |
| 项目级，随项目共享 | `<项目根目录>/.agents/skills/mindplus-agent-skill/` |

Windows 用户级安装示例：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE/.agents/skills" | Out-Null
git clone https://gitee.com/mind-plus/mindplus-agent-skill.git "$env:USERPROFILE/.agents/skills/mindplus-agent-skill"
```

如果目标已存在，不必再次 clone。安装后查看技能列表；CLI / IDE 可用 `/skills`，并通过 `$` 选择技能：

```text
$mindplus-agent-skill 帮我把 D:/extensions/v1-demo 转换到 D:/extensions/v2-demo，只做转换和基础检查。
```

桌面端也可在技能界面选择后补充任务。未识别时重开会话或重启客户端。已有版本若使用其他技能目录，应以该客户端显示的实际来源为准，避免重复安装同名副本。见 [Codex 官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

### Claude Code

将整个目录放到 `~/.claude/skills/mindplus-agent-skill/`（用户级），或 `<项目根目录>/.claude/skills/mindplus-agent-skill/`（项目级）。

Windows 用户级安装示例：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE/.claude/skills" | Out-Null
git clone https://gitee.com/mind-plus/mindplus-agent-skill.git "$env:USERPROFILE/.claude/skills/mindplus-agent-skill"
```

在 Claude Code 中调用：

```text
/mindplus-agent-skill 审核 D:/extensions/v2-demo，使用 BASIC，只报告问题和建议。
```

也可通过自然语言明确要求使用该技能。若会话启动时尚不存在技能父目录，安装后重启会话。见 [Claude Code 官方技能文档](https://code.claude.com/docs/en/skills)。

### WorkBuddy

推荐使用官方的本地技能包导入入口：

1. 准备包含完整技能目录的本地技能包；压缩时排除 `.git`、缓存和运行记录，保留脚本及参考资料。
2. 打开 **技能 → 添加技能 → 上传技能**，选择本地技能包并导入。
3. 在已安装列表中确认 `mindplus-agent-skill` 已启用，并让任务可以访问扩展所在目录。
4. 在对话中明确说明：

```text
请使用 mindplus-agent-skill，为这个传感器创建 Mind+ V2 上传模式扩展。
需求和库源码在 D:/extensions/sensor-source，输出到 D:/extensions/sensor-v2。
先整理规格并完成创建和基础检查，不发布。
```

以当前客户端导入窗口支持的包格式为准。若本地包不能导入，可先用下方 Others 的显式文件方式；不要用“创建技能”重新生成一份同名规则代替原包。见 [WorkBuddy 本地技能导入说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)。

### ZCode

用户级目录为 `~/.zcode/skills/mindplus-agent-skill/`。Windows 示例：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE/.zcode/skills" | Out-Null
git clone https://gitee.com/mind-plus/mindplus-agent-skill.git "$env:USERPROFILE/.zcode/skills/mindplus-agent-skill"
```

安装后进入 **设置 → 技能 → 刷新**，确认已启用；在对话中输入 `$` 选择：

```text
$mindplus-agent-skill 检查 D:/extensions/v2-demo 的配置和资源引用，使用 BASIC。
```

如果已在 Codex 或 Claude Code 安装，也可以从 ZCode 的 **设置 → 技能 → 导入** 扫描外部技能，并选择复制或软链接；复制为独立副本，软链接需要来源目录持续可用。见 [ZCode 官方技能文档](https://zcode.z.ai/cn/docs/skill)。

### Others：其他 Agent

支持 Agent Skills 目录的工具，可以按其文档将完整目录放入技能搜索路径；不同工具的目录和调用符号可能不同，不要默认都使用 `.claude/skills` 或 `$`。

没有原生 Skill 功能，但能读文件和执行命令的工具，可以把仓库放在可访问的位置，在任务开始时明确指定入口：

```text
请先完整读取 D:/tools/mindplus-agent-skill/SKILL.md，
以该目录为技能根目录，按路由只加载本次需要的参考文件，
使用其 scripts 中的工具完成任务。

本次目标：将 D:/extensions/v1-demo 转换到 D:/extensions/v2-demo。
只转换和基础检查，不发布，不做 HOST_READY 验收。
```

也可以在该工具支持的项目指令文件中保留这段入口提示。只支持聊天、无法访问技能目录或运行脚本的工具，可以讨论方案，但不能直接执行本项目的完整流程。

## 常用任务怎么提

安装完成后，通常直接给 Agent 自然语言需求即可，不需要手写 handoff 或记住脚本参数。

| 目标 | 提示词示例 |
| --- | --- |
| 新建 | “使用 mindplus-agent-skill，为这个库创建 V2 扩展，先确认积木功能，输出到一个新目录。” |
| 转换 | “将这里的 V1 转换为 V2，保留默认行为，只做基础检查。” |
| 普通审核 | “用 BASIC 审核这个扩展，列出具体问题，不修改文件。” |
| 创建后发布 | “完成创建和基础检查后，提交并推送到我指定的 Gitee 仓库。” |
| 独立发布 | “将当前项目提交并推送到指定仓库和分支，不追加完整 Mind+ 验收。” |
| 完整验收 | “对这个扩展执行 HOST_READY 验收，列出需要我在 Mind+ 中确认的项目。” |

创建／转换请提供来源和新的输出目录；发布请给出明确目标和提交／推送授权。创建新仓库还需说明可见性。没有明确要求完整验收时，不必主动补充 Mind+ 界面确认。

## 目录导览

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | Agent 入口、路由和主要边界 |
| [scripts/mpa.py](scripts/mpa.py) | 启动、交接、推进、恢复与清理 |
| [references/workflows/](references/workflows/) | 四个叶流程及按需加载的完整验收说明 |
| [references/switch/](references/switch/) | 创建和转换共用的模式、规范和参考资料 |
| [references/contracts/](references/contracts/) | 请求、规格和 handoff 的数据结构 |
| [scripts/switch/](scripts/switch/) | 来源分析、脚手架和静态检查工具 |
| [agents/openai.yaml](agents/openai.yaml) | Codex 展示和调用元数据 |
| [tests/](tests/) | 路由、校验、发布及回归测试 |

进一步了解实现约定，可阅读 [架构说明](references/architecture.md)、[证据与审核等级](references/evidence.md) 和 [结果交接协议](references/handoff.md)。

## 版本更新

- V0.1.2
   - 内置 WB 打包工具与发布配置，添加 Gitee Go 标签发布工作流
   - 自动生成 WB ZIP、核对附件内容并维护发行版下载说明
- V0.1.0
   - 初始化第一个版本
- V0.1.1
   - 添加自动更新逻辑，确保语料库处于最新状态
   - 修复 V1 转 V2 中关于 string 的处理

## WB 打包与自动发行

`release-info.json` 中的 `marketplace_introduction` 和 `marketplace_prompts` 是本项目的文案配置，后者每行一条提问。每次打包会在 ZIP 同级生成 `marketplace-info.md`，分别提供市场后台的“介绍”和“试试这样问我”。它不进入 ZIP，也不写入 SKILL.md；[WorkBuddy 官方文档](https://open.workbuddy.cn/docs/skill) 尚未说明这两项的自动导入字段，需要在后台填写。

仓库内只维护一个发布工具：[tools/pack_workbuddy.py](tools/pack_workbuddy.py)。配置位于 [release-info.json](release-info.json)，保持 `version`、[VERSION](VERSION) 和 SKILL.md 中的版本元数据一致。打包产物放在被 Git 忽略的 `dist/`；开发工具、流水线和发布配置不进入 WB ZIP。

本地运行（Python 3.9+，无第三方依赖）：

```sh
python -X utf8 -B tools/pack_workbuddy.py
```

[Gitee Go 工作流](.workflow/release-workbuddy.yml) 在推送 `vX.Y.Z` 标签时执行打包和发布。首次使用需在仓库的 Gitee Go 页面启用／导入该工作流，并配置有本仓库 Release 写入权限的凭据。在「通用变量」中创建 `MP_RELEASE_TOKEN`，类型选「文本」，勾选「密文」，填写 Token 后保存。工作流已通过以下声明引用该变量，仓库中只保存名称：

```yaml
variables:
  global:
    - MP_RELEASE_TOKEN
```

仅创建通用变量不会自动传入流水线；图形界面的等效操作是「编辑流水线 → 图形视图 → 变量设置 → 添加变量 → 通用变量 → MP_RELEASE_TOKEN」。密文由 Gitee Go 在运行时提供，脚本无需自行解密，只读取 `MP_RELEASE_TOKEN`，日志仅报告是否可用。不要将实际 Token 写进 YAML、仓库或日志。手动运行时需选择包含上述声明的分支；此文件本身不会开通 Gitee Go 服务。

发布 `0.1.2` 时，先提交版本和代码，再执行：

```sh
git tag v0.1.2
git push origin v0.1.2
```

工具核对本地标签、远程标签和构建提交一致后，创建或更新对应 Release，上传 `mindplus-agent-skill-0.1.2-workbuddy.zip`；通用版使用 Gitee 自带源码 ZIP。发行说明仅维护 `mindplus-pack` 标记区，保留手写内容和现有标题。同名附件内容相同则复用，不同则失败，绝不自动删除或覆盖；网络中断可重跑以核对已有状态。检查失败不会进入发布；创建或上传后的失败会保留已完成部分，供重跑恢复。

需要本地执行同一发布过程时，配置上述凭据后使用 `python tools/pack_workbuddy.py --publish --tag v0.1.2`。普通打包命令不会访问发布 API。工作流直接使用 Gitee 构建镜像内的 Python 3.9，不安装 uv，也不从 GitHub 下载 Python。

工作流依据：[触发规则](https://help.gitee.com/gitee-go/pipeline/trigger)、[构建插件](https://help.gitee.com/gitee-go/plugin/ci-build)、[Release API](https://gitee.com/sdk/gitee5j/blob/main/docs/RepositoriesApi.md)。本地测试不代表已在云端执行成功。

