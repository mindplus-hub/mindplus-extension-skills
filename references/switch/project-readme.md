# 最终项目 README 约定

Builder 根目录就是最终 V2 项目根目录，根 `README.md` 必须在构建前根据实际扩展改写，
不能保留 Builder 模板占位符。

## 证据顺序

1. 转换后的 `extension/public/config.json`。
2. `extension/index.js`、locales、积木定义和实际资源。
3. V1 的 README、配置、产品型号、示例和截图。
4. Builder 根 README 模板，只提供章节结构，不提供业务事实。

不得根据产品名称猜测 SKU、功能、兼容主板或性能参数。必要事实无法证明时写入运行日志，
进入敏感节点，不生成虚构内容。

## 最低内容

- 扩展标题和事实性简介。
- 产品/型号/SKU：只有源证据存在时填写。
- 主要积木说明。
- 示例程序或已有示例资源说明。
- 支持列表，与 `supportDevices`、`supportArch` 和实际 board 条件一致。
- 初始 V2 版本更新记录。
- 开发文档或产品资料链接：仅保留已知链接。

图片必须使用项目内真实存在的相对路径。不要生成、重画或复制不存在的截图。

## 确定性检查

写完后运行：

```text
python scripts/switch/check_project_readme.py --project-root <project_root> --output <run_root>/record/readme-check.json
```

检查失败时不得开始 `npm run build`。该检查只证明模板占位符、必需章节和本地链接通过，
不证明文案、产品信息或设备兼容性已经完成独立审核。
