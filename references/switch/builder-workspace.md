# 最终 Builder 项目与一次有界安装/构建

## 布局

```text
<work_root>/
├── .mindplus-agent/
│   └── runs/<parent_run_id>/children/CONVERT_FRESH/
│       ├── record.json
│       ├── log.md
│       └── record/
└── ext2-<mode>-<safe-id>/             # Git-free Builder scaffold，也是最终项目根目录
    ├── extension/              # 唯一 V2 扩展源码目录
    ├── README.md               # 必须根据当前扩展改写
    ├── package.json
    ├── package-lock.json
    ├── webpack.config.js
    ├── scripts/
    ├── utils/
    └── build/
```

`.mindplus-agent` 只保存运行记录，不保存最终 Builder。不得再创建
`<run_root>/builder` 或额外的“成品副本”。

## 项目根目录门禁

1. 先按 [项目目录命名](../project-naming.md) 确定以 `ext2-` 开头的外层目录，再使用用户明确指定的 `project_root`。如果用户给出的是父目录（本身不是目标项目、且已存在其他内容）时，不得直接在其下沿用 V1 目录名；必须派生 ext2-<mode>-<safe-id> 作为 project_root。
2. 未指定时，只有 V1 `id` 已经是无歧义安全目录名，才可派生
   `<work_root>/ext2-<mode>-<id>`；否则询问。
3. `project_root` 不得位于 V1 源目录或 `.mindplus-agent` 内，也不得包含 V1 源目录。
4. 目标必须不存在或为空。非空目录、已有 Git 项目或同名成品都必须停止，不能覆盖。
5. 执行：

```text
python scripts/switch/prepare_builder_scaffold.py --project-root <project_root> --output <run_root>/record/builder-scaffold.json
```

脚本按语义版本选择 Gitee 的最新稳定 Release 附件
`mindplus-ext2-builder-Scaffold.zip`，兼容文件直接在 ZIP 根部或单层包装目录，解压后直接形成
`project_root`。不得改用标签的 Source code ZIP/TAR 或 `git clone`；它们会重新带入 Builder
仓库历史或 `examples/`。

脚手架准备完成必须满足：没有任何 `.git/`、`examples/`、`node_modules/` 或 `build/`；存在
`extension/`、`package.json`、`package-lock.json`、`scripts/`、`utils/` 和 Webpack 配置。
本 Skill 不自动执行 `git init`、添加用户 Gitee remote、commit 或 push；用户明确提出后才能把
这个干净目录初始化为用户自己的仓库。

## 一次安装与卡住交接

在最终 `project_root` 执行一次：

```text
npm install
```

命令启动前先准备一份命令输出记录；命令启动的同一时刻写
`install_attempt: 1`。这是一次有界尝试，不是让 Agent 无限等待。默认观察窗口为：

- 连续 120 秒没有新的 stdout/stderr、文件变化或包管理进度；或
- 总等待时间达到 10 分钟；或
- 主机明确报告 `nvm` 默认 Node 未设置、EPERM/锁占用、cacache/socket 卡死等环境问题。

满足任一项就认定本次安装 `STALLED`。停止等待，不用 `npm ci`，不清理或修复环境，
也不重新启动 `npm install`。将 `install_status` 写为 `USER_ACTION_REQUIRED`，
`install_exit` 写为 `TIMEOUT` 或 `HOST_BLOCKED`，`install_stall` 写入可复现的原因，
并将 `user_action_required` 写为 `RUN_NPM_INSTALL_AND_BUILD`。安装卡住不丢弃已经准备好的
转换任务；继续 S5--S9 的 V1 快照、转换、README 和静态扫描，最后把构建记为
`SKIPPED_DEPENDENCY`。如果终端工具仍有子进程，
不要启动第二个命令；只有在工具明确标识它是本次命令的子进程时才可结束它，否则把进程
清理交给用户。

正常退出码 0 才是 `install_status: PASS`。其他非零退出是
`install_status: FAIL`、`BLOCKED/BUILD_ENV`，同样不得自动重试。无论哪种结果，都记录
Node/npm 版本、退出码和 `package-lock.json` 前后状态。`node_modules` 是环境产物，不作为
转换内容汇报或提交。

## 转换写入范围

确认 Builder 根入口面向根 `extension/` 后，才可替换其示例 scaffold。转换业务内容只写：

- `project_root/extension/`
- `project_root/README.md`
- `run_root/record/`

Builder 的 `utils/`、`scripts/`、`package.json` 和 Webpack 配置保持模板状态；脚手架本身不得
含 `examples/` 或 `.git/`，`npm install` 自身导致的 lockfile 变化单独记录。不得使用
`extensions/<id>`、`npm_config_target` 或再复制一个 Builder。

## 一次构建与卡住交接

构建前必须满足：

- `extension/index.js`、`extension/func.js`、`extension/public/config.json` 存在且可解析；
- 复制映射与语义矩阵完成；
- 根 README 已改写且 `check_project_readme.py` 通过；
- `install_attempt: 1` 且 `install_status: PASS`；
- `build_attempt: 0`。

随后只执行一次：

```text
npm run build
```

命令启动立即写 `build_attempt: 1`，使用与安装相同的有界观察窗口。若无进展、超时、
锁占用或其他主机问题导致卡住，写 `build_status: USER_ACTION_REQUIRED`、
`build_exit: TIMEOUT` 或 `HOST_BLOCKED`、`build_stall` 的具体原因，并将
`user_action_required` 写为 `RUN_NPM_BUILD`。这时把 `S10` 和 `S11` 记为已处理的
`BLOCKED`，最终状态为 `HANDED_OFF`，不得修复后重跑。若安装没有通过，根本不要启动构建，
写 `build_status: SKIPPED_DEPENDENCY`、`build_exit: NOT_RUN`，交接用户执行安装和构建。

只有退出码 0、新鲜目标 `main.js` 和预期 `public/` 资源都存在时才是构建 Pass。它只证明
Builder 打包，不证明 Mind+ 导入、目标代码编译、上传、运行或设备行为。

## 日志状态约定

顶部字段是机器可读摘要，`Event Log` 是追加的证据链；两者都必须更新。建议使用：

```text
install_status: NOT_RUN | PASS | FAIL | USER_ACTION_REQUIRED
install_exit: NOT_RUN | 0 | NONZERO | TIMEOUT | HOST_BLOCKED
install_stall: NONE | NO_PROGRESS | HOST_TIMEOUT | HOST_LOCK | NETWORK | ENVIRONMENT
build_status: NOT_RUN | PASS | FAIL | USER_ACTION_REQUIRED | SKIPPED_DEPENDENCY
build_exit: NOT_RUN | 0 | NONZERO | TIMEOUT | HOST_BLOCKED
build_stall: NONE | NO_PROGRESS | HOST_TIMEOUT | HOST_LOCK | NETWORK | ENVIRONMENT | INSTALL_NOT_PASSED
user_action_required: NONE | RUN_NPM_INSTALL_AND_BUILD | RUN_NPM_BUILD
```

事件中出现 `S4 PASS`、`S9 PASS` 或 `S10 BLOCKED` 后，必须同步更新对应摘要字段；
不能只追加事件而保留 `NOT_RUN`。`BLOCKED` 表示该步骤已得到终态，不表示成功；日志脚本
会将 `PASS`、`FAIL`、`BLOCKED` 都标记为已处理，只有 `RUNNING` 保持未完成。

## 版本选择与模板文件

每个新项目在准备时解析一次最新稳定版，记录 Release tag、附件 URL 和下载 SHA-256；运行中不因远端出现新版而替换已展开的脚手架。跳过草稿和预发布，按版本号比较，不依赖 API 返回顺序。最新稳定版缺少专用 Scaffold 附件或网络失败时明确报告，不退回旧版本、自动源码 ZIP 或 Git 克隆。

沿用所选附件的 `.gitignore` 和工具文件，不用旧模板覆盖。运行日志写在既定工作记录目录，不能仅依靠 `.gitignore` 判断文件是否适合发布；发布仍检查实际文件集合和敏感信息。已有 V2 升级不自动替换 Builder。

若 Release 提供同名 `.zip.sha256`，下载后必须比对；没有时记录 `checksum_status: RECORDED_ONLY`，不得声称发布方摘要已验证。脚手架与 Skill 自升级是独立下载流程：Skill 自升级仍强制要求摘要文件。显式本地 `--archive` 必须同时提供 `--sha256`，不为本地包声称“最新版本”。
