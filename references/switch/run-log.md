# 运行日志约定

默认位置：`<work_root>/.ms/<run_id>/log.md`。`.ms` 只是收纳目录，不是权限边界；
不要写入凭据、令牌、私有 Wiki 内容或用户源码正文。

## 初始模板

```markdown
# MindPlus-Switch Run Log

- run_id: <id>
- v1_source: <absolute path>
- work_root: <absolute path>
- run_root: <absolute path>
- project_root: NOT_SELECTED
- extension_root: NOT_CREATED
- status: RUNNING
- current_step: S-1 OPEN_RUN_LOG
- mode: UNKNOWN
- review_policy: AUTO
- reference_status: NOT_RUN
- reference_release: NOT_RUN
- reference_root: NOT_RUN
- reference_selection: NOT_RUN
- install_attempt: 0
- build_attempt: 0
- install_status: NOT_RUN
- install_exit: NOT_RUN
- install_stall: NONE
- build_status: NOT_RUN
- build_exit: NOT_RUN
- build_stall: NONE
- user_action_required: NONE
- next_workflow: NOT_RUN
- review_status: NOT_RUN
- identity_mapping: NOT_RUN
- compatibility_id: NOT_RUN
- conversion_check: NOT_RUN
- copy_check: NOT_RUN
- readme_check: NOT_RUN

## Checkpoints

- [x] S-1 OPEN_RUN_LOG
- [ ] S0 CHECK_REFERENCE_RELEASE
- [ ] S1 ROUTE
- [ ] S2 LOAD_REFERENCES
- [ ] S3 PREPARE_PROJECT_ROOT
- [ ] S4 NPM_INSTALL
- [ ] S5 VERIFY_V1_SNAPSHOT
- [ ] S6 SEMANTIC_MATRIX
- [ ] S7 IMPLEMENT_EXTENSION
- [ ] S8 UPDATE_README
- [ ] S9 STATIC_CONVERSION_CHECKS
- [ ] S10 BUILD_ONCE
- [ ] S11 HANDOFF

## Route Evidence

- candidates: <mode + evidence paths + confidence>
- selected: NONE
- source_anomalies: NOT_RUN
- intervention: NONE

## V1 Snapshot Evidence

- initial_inventory: NOT_RUN
- pre_conversion_inventory: NOT_RUN
- snapshot_compare: NOT_RUN
- snapshot_match: NOT_RUN

## Reference Evidence

- status: NOT_RUN
- release_id: NOT_RUN
- content_sha256: NOT_RUN
- supported_modes: NOT_RUN
- active_root: NOT_RUN
- selection_file: NOT_RUN
- topics_loaded: NOT_RUN

## Builder Evidence

- scaffold_release: NOT_RUN
- scaffold_url: NOT_RUN
- scaffold_sha256: NOT_RUN
- inherited_git: NOT_RUN
- examples_present: NOT_RUN
- node_version: NOT_RUN
- npm_version: NOT_RUN
- npm_install_exit: NOT_RUN
- package_lock_change: NOT_RUN

## Decisions and Risks

- <decision>: <fact, evidence, owner, result>

## Event Log

- [timestamp] [S-1] created run log
```

## 更新规则

1. 进入步骤前更新 `current_step`，完成或终止后再勾选；`PASS`、`FAIL`、`BLOCKED`
   都表示该步骤已有终态，只有 `RUNNING` 保持未勾选。
2. Event Log 只追加；顶部状态可以更新，但不能删除历史。
3. Release 检查在路由前执行；模式 Reference 只在路由后读取。
4. Topic 选择器只有 `PASS` 才能继续；记录 selection 文件和实际读取的 Topic ID。
5. 等待或阻断前写入候选、证据、已发生写入和下一步。
6. `npm install` 或 `npm run build` 一旦启动，对应 attempt 立即从 0 改成 1；每个阶段
   只允许一次有界尝试。卡住时使用 `USER_ACTION_REQUIRED` 和 `user_action_required`，
   不得用第二次尝试“验证”。
7. 运行恢复时以实际文件、manifest、缓存和 Builder 复核日志，不盲信旧状态。
8. 日志无法写入时立即 `BLOCKED/WORKSPACE`。
9. 每个步骤结束调用 `scripts/switch/update_run_log.py --log <log> --step <Sx> --result <PASS|FAIL|BLOCKED|RUNNING> --event <summary>`；用重复的 `--field KEY=VALUE` 同步更新脚本允许的顶部事实。事件和摘要不能互相矛盾。
10. 最终交付前调用 `scripts/switch/check_run_log.py --log <log>`。完成态仍为 `RUNNING`、`S-1`、
    `S11` 未处理、已执行阶段仍为 `NOT_RUN`，或成功阶段的依赖状态不一致时，不得交付。

## 终态矩阵

| 情况 | 顶部 `status` | 安装/构建摘要 | 下一步 |
|---|---|---|---|
| 安装与构建都通过 | `CONVERTED_BUILD_PASS` | `PASS / PASS` | 独立 review |
| 安装非零退出 | `BLOCKED` | `FAIL / NOT_RUN` | 用户处理构建环境 |
| 安装卡住或主机锁死 | `HANDED_OFF` | `USER_ACTION_REQUIRED / SKIPPED_DEPENDENCY` | 用户运行 `npm install`、`npm run build` |
| 构建卡住或主机锁死 | `HANDED_OFF` | `PASS / USER_ACTION_REQUIRED` | 用户运行 `npm run build` |
| 静态转换门禁失败 | `BLOCKED` | `NOT_RUN / NOT_RUN` 或已发生的真实状态 | 修复转换后新开 run |

`HANDED_OFF` 不是构建成功；它只表示转换和已经执行的静态步骤已记录，构建验证由用户接手。

安装阶段若因卡住而 `BLOCKED`，允许继续记录 S5--S9；这是唯一允许在 S4
终态后继续的情况。安装非零失败、静态门禁失败或其他 `BLOCKED` 都只能直接进入 S11。
