# 新建库命名

CREATE_FRESH 与 CONVERT_FRESH 在 `mpa.py start` 冻结路径前，按实际运行模式确定新库名称及外层项目文件夹：

| 模式 | 名称格式 |
| --- | --- |
| 实时模式 | `ext2-rt-<库名称>` |
| 上传模式 | `ext2-ul-<库名称>` |
| Python 模式 | `ext2-py-<库名称>` |
| MicroPython 模式 | `ext2-mpy-<库名称>` |

- 模式前缀固定小写。库名称以英文字母或数字开头，其余使用英文字母、数字、连字符或下划线；名称不明确时只询问缺失信息。
- 先确认运行模式再生成名称。现有 `UPLOAD` 对应 `ul`，`PYTHON_BLOCK` 对应 `py`；命名约定不增加 Skill 尚未支持的实时或 MicroPython 创建／转换能力，不得为了通过路由伪装成已有模式。
- 只添加一次前缀。例如上传库 `sensor` → `ext2-ul-sensor`。来源名称为 `ext2-sensor` 时取业务名称 `sensor`，不叠成 `ext2-ul-ext2-sensor`；已有模式前缀必须与实际模式一致，不一致时先纠正拟建名称。
- 用户给出父目录时，在其下创建上述名称的子目录。显式目标不合规时，说明并确定符合约定的目标再启动，不静默改写已冻结路径。路由、转换初始化和脚手架均校验格式。
- 新建远端仓库无另行指定名称时沿用目录名；显式指定的新名称也必须符合四类格式，并与目录及已知 config.mode 的模式前缀一致。建仓请求明确传入 path，回读 full_name 必须与授权目标一致。已有远端目标不擅自重命名。前缀不加入 `config.id`，不改变 Builder 的 `extension/`、构建产物名称和旧兼容身份。
- UPGRADE_EXISTING、REVIEW_EXISTING、PUBLISH_GITEE 保留已有路径；fork 已有 V2 不为此自动改名。

这是新建前的路径约束，不受 P1 命名建议豁免；空目录、来源隔离、模式支持范围和授权条件仍同时适用。

## Lite 查重后的作者后缀

路由后的 Lite 以同模式、同类型的 config.author + config.id 判同一库，并选用已有库／fork。只有 id 相同而 author 不同时，新文件夹使用 `ext2-<mode>-<库名称>-<作者id>`；中文作者转换为已确认的拼音，只追加一次后缀。保留四类模式前缀及 config.id。此约束不被 P1 命名建议豁免。

目录变化发生在项目写入之前；已有运行保留记录，使用新路径重新 start，不改写旧请求。新远端默认沿用这个目录名；现存远端不自动改名。Lite 证据中的 original_folder/author/author_slug 由验证器核验与实际路径相符。
