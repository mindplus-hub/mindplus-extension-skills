# 新建项目目录命名

CREATE_FRESH 与 CONVERT_FRESH 的最终外层项目目录统一为 `ext2-<name>`，在 `mpa.py start` 冻结路径之前确定；路由和脚手架入口都会检查小写 `ext2-` 前缀及非空后缀。

- 从明确的项目名称或来源 ID 提取安全目录名，添加一次 `ext2-`；已有此前缀时保留。例如 `espnow` → `ext2-espnow`。名称不明确时只询问缺失的名称。
- 用户给出父目录时，在其下创建 `ext2-<name>`；不能把父目录本身当成项目。Agent 传入的 `project_root` 不代表用户要求省略前缀。
- 不直接沿用 V1 目录名、Builder 仓库名或脚手架压缩包根目录名。显式目标路径不符合约定时，先说明并确定符合约定的目标，再启动；不得悄悄改写已冻结的运行路径。
- 前缀只约束新项目外层目录，不改写 `config.id`、Builder 的 `extension/`、构建产物名称或已指定的远端仓库地址。
- UPGRADE_EXISTING、REVIEW_EXISTING、PUBLISH_GITEE 保留已有项目路径；fork 已有 V2 也不为此自动改名。

这是创建前的路径约束，不属于发布审核中可忽略的 P1 命名风格建议。空目录要求、来源隔离和用户授权仍同时适用。
