# 本地资料与 Release 更新

每次转换都先执行 `scripts/switch/check_reference_release.py`。脚本只检查一个固定的
`latest.json`，不会访问或解析 Wiki，也不会修改已安装 Skill。

## 当前资料范围

- `references/switch/generated/` 是随 Skill 发布的已验证基线。
- 当前 HIR Release 同时覆盖 `UPLOAD` 与 `PYTHON_BLOCK`。
- reference bundle 已随 `mindplus-extension-skills` 内置；稳定公开清单地址尚未确定前，
  `references/switch/release-channel.json` 保持禁用且不配置独立 switch 仓库回退。
- 若旧缓存缺少当前 bundled 已提供的模式，检查器优先使用 bundled，避免旧的仅上传资料阻断
  Python 路由；覆盖模式不减少的已验证缓存仍可使用。

## 启动命令

```text
python scripts/switch/check_reference_release.py --skill-root <skill_root> --output <run_root>/record/reference-state.json
```

脚本输出的 `active_root` 是本次唯一可用的生成资料根目录。路由后运行：

```text
python scripts/switch/select_reference_topics.py --inventory <run_root>/record/v1-inventory.initial.json --reference-state <run_root>/record/reference-state.json --mode <UPLOAD-or-PYTHON_BLOCK> --output <run_root>/record/reference-selection.json
```

只加载 `reference-selection.json` 返回的 Topic 路径，不一次读取全部 Field/API 文档。选择器会
核对模式、manifest 声明、文件路径和 SHA-256；观测到但没有路由映射的特征会阻断。

## 状态

| 状态 | 动作 |
| --- | --- |
| `BUNDLED_ONLY` | 远程频道未配置，使用随 Skill 发布的基线 |
| `LOCAL_CACHE` | 使用上次已验证的全局缓存 |
| `UNCHANGED` | 远端与本地 release/content hash 相同，不下载 ZIP |
| `UPDATED` | 新 ZIP、manifest 和每个文件哈希均通过，已原子激活 |
| `STALE_CACHE` | 远端检查失败，继续使用已验证缓存并警告 |
| `BUNDLED_FALLBACK` | 远端检查失败且无更完整缓存，使用已验证的 bundled 基线 |
| `BLOCKED` | bundled、缓存和下载包都没有可验证版本 |

`STALE_CACHE` 和 `BUNDLED_FALLBACK` 可以继续，但必须写入日志和最终结果。资料包只能
包含 Markdown/JSON 数据；下载内容不能覆盖 `SKILL.md`、脚本或人工规则。

## Gitee 发布协议

维护者发布首个可下载版本后，将 `release-channel.json` 的 `channel_url` 设置为公开、稳定的
`latest.json` HTTPS 地址并启用频道。`latest.json` 至少包含：

```json
{
  "schema_version": 1,
  "bundle_id": "mindplus-switch-references",
  "release_id": "refs-<content-hash>",
  "bundle_url": "https://gitee.com/<owner>/<repo>/releases/download/<tag>/<zip>",
  "bundle_sha256": "<sha256>",
  "content_sha256": "<manifest content hash>",
  "supported_modes": ["UPLOAD", "PYTHON_BLOCK"],
  "min_skill_version": "0.5.0"
}
```

运行时下载只更新用户缓存。发布、上传附件、commit 和 push 都是维护者动作，不由转换
任务自动执行。
