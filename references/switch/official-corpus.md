# 官方语料检索协议（official corpus fallback）

内置语料（generated Wiki 事实、conventions 词典、block-organization）无法解答时的
**第一回退层**：检索 Mind+ 官方 Gitee 组织 `https://gitee.com/organizations/mind-plus/projects`。
本协议对 CREATE 与 CONVERT 同效。

## 证据等级与边界

- 官方组织仓库中的已发布扩展源码按 **C2（官方已发布行为）** 记录，高于普通本地示例，
  低于 C3 脚本事实。引用时必须记录仓库、路径、commit/ref、URL 和文件 SHA-256。
- **只读**：仅 GET 公开接口，不登录、不使用 token、不评论、不 fork、不提交 issue。
- 只读取数据文件（config.json、index.js、func.js、locales、README、docs），
  **不执行**下载的任何代码，不引入其依赖。
- 官方仓库内容回答"官方怎么做"，不改变本 Skill 的门禁：字段白名单、设备字典、
  静态检查器仍然强制；官方项目与内置语料冲突时按敏感节点暂停，不默认谁对。

## 工具

```text
python scripts/switch/fetch_official_reference.py list [--search <关键词>] [--page <n>]
python scripts/switch/fetch_official_reference.py tree --repo <名称> [--path <目录>] [--ref <分支>]
python scripts/switch/fetch_official_reference.py fetch --repo <名称> --path <文件路径> [--ref <分支>] --evidence-dir <run_root>/record/official-corpus
```

- `list`：分页列出组织仓库，`--search` 按名称/描述客户端过滤。
- `tree`：列出仓库某目录的文件清单（查 config.json 在哪个扩展里）。
- `fetch`：下载单个文件到 evidence 目录，并写同名的 `.provenance.json`
  （url、repo、path、ref、sha256、fetched_at）。证据文件路径写进 run log / spec。

典型用法：目标板不在 device-ids.json 时，`list --search <板名或模块名>` 找官方扩展，
`tree` 定位其 `extension/public/config.json`，`fetch` 拉取并从 `supportDevices` 读出设备 ID。

## 与词典的回填关系

从官方仓库学到的**可复用**惯例（新设备 ID、新字段用法、新组织模式）应当作为
词典更新提案交给维护者（带本协议的 provenance 证据）合并进 device-ids.json / conventions.md；
运行中不得直接修改词典。一次性、项目特定的结论只记录在本次 run 的证据目录里。
