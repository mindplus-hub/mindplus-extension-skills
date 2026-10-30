# 扩展能力案例

按能力检索，不按仓库整体评优。下列为 2026-10-27 读取的公开源码固定提交；仅确认源文件内容及摘要，没有执行下载代码，也没有据此证明原生显示、编译或硬件效果。规范仍以对应模式文档和 Wiki Topic 为准。本页仅提供已整理的能力参考，不要求使用者采集仓库或提炼、回填语料。

| 当前问题 | 读取案例 | 适用模式 |
| --- | --- | --- |
| Tx/Rx 下拉框为什么少、默认值如何选 | 引脚能力与底层串口实现 | UPLOAD |
| 初始化对象后如何返回可组合表达式 | 实例初始化与 reporter | PYTHON_BLOCK |
| 图像转码片段能否单独复用 | 隐式依赖与反例 | PYTHON_BLOCK |

## 引脚能力与底层串口实现

- 来源：`mind-plus/ext2-ul-hss77-pl`，提交 `81aaca56a6f6078910a25a20c2e084de47148da6`。[index.js](https://gitee.com/mind-plus/ext2-ul-hss77-pl/blob/81aaca56a6f6078910a25a20c2e084de47148da6/extension/index.js)、[config.json](https://gitee.com/mind-plus/ext2-ul-hss77-pl/blob/81aaca56a6f6078910a25a20c2e084de47148da6/extension/public/config.json)。
- 观察：在 `getInfo()` 获取 runtime 引脚；经典 Uno/Nano 使用 `DIGITAL_WRITE` / `DIGITAL_READ`，其他声明主板使用 `UART_TX` / `UART_RX`。默认值取当前菜单，RX 优先选择与 TX 不同的有效值，空菜单使用空默认值。
- 可取之处：能力查询跟随主板变化，避免维护一份固定 GPIO 表；默认值不脱离返回列表。移植前仍须核对底层库实际采用软串口还是硬件 UART。
- 限制：经典 Uno/Nano 的判断不能推广到 Mega、Leonardo 或 Nano Every。不要按参数叫 Tx/Rx 就固定选 UART，也不要把 AVR PCINT 等同于外部中断。更不能用“列表多”证明引脚可用。
- 采用时同时核对 runtime API 最低版本、主板映射和 `supportDevices` 最低版本；方法见 [上传模式指南](upload-mode.md) 与 [引脚规范](generated/upload/pins.md)。本案例不扩大已声明或已验证的设备范围。
- 原始文件 SHA-256：`index.js` 为 `794362d8f190a2030af6bc0f427cfa4445fe78106bfeeeed68da0af9cbce15e3`；`config.json` 为 `12c32610e609cd0a5a078bfc04ecdcbe5b24c49dc57c8c31d5ee2381a03046c8`。

## 实例初始化与 reporter

- 来源：`mind-plus/ext2-py-analogvoltage`，提交 `05e4dc2499ece0683a7cb1281d768b9176afa00c`。[func.js](https://gitee.com/mind-plus/ext2-py-analogvoltage/blob/05e4dc2499ece0683a7cb1281d768b9176afa00c/extension/func.js)、[index.js](https://gitee.com/mind-plus/ext2-py-analogvoltage/blob/05e4dc2499ece0683a7cb1281d768b9176afa00c/extension/index.js)。
- 观察：初始化方法以 `generator.addImport(...)` 生成模块导入，在积木当前位置返回对象赋值；读取方法使用同一 `OBJ.code`，返回 `[表达式, generator.ORDER_UNARY_POSTFIX]`。index 分别声明 COMMAND 和 REPORTER。
- 可取之处：导入、当前位置初始化、表达式返回各有职责；对象名由积木参数传递，可支持多个实例。适用条件是初始化先执行、对象在消费者作用域内且参数生成有效 Python 表达式。
- 限制：`PIN` 默认 `pin1` 是变量引用，不是可直接工作的硬件引脚常量；源码片段没有证明该变量在哪里初始化，也没有证明 `dfrobot_analog_voltage` 在目标环境可用。不能把默认示例与依赖部署一并认定为通过。
- 使用 reporter 时结合实际返回类型选择合法消费者；不把所有 reporter 接到数值等待槽。规则见 [Python 模式指南](python-block-mode.md) 与 [Basic 场景有效性](../review-basic.md)。
- 原始文件 SHA-256：`func.js` 为 `a8db72f32a0971d71774fac2ff24b92b0e4ee233a056af97d51c4382276d3c46`；`index.js` 为 `4ffb4580a83bdbed6086960fa4953e346fbf2bc99de1becce5bbf025b55638ef`。

## 隐式依赖与反例

- 来源：`mind-plus/ext2-py-base64`，提交 `608e4da7b72fc3657296f8e09ca2d9dd03c855c9`。[func.js](https://gitee.com/mind-plus/ext2-py-base64/blob/608e4da7b72fc3657296f8e09ca2d9dd03c855c9/extension/func.js)。
- 观察：初始化生成 `base64`、`BytesIO`、`Image` 导入与辅助函数；`frame2base64` 使用 `cv2.cvtColor(...)`，该文件没有生成 `import cv2`。图片路径 reporter 还引用 `get_asset_path_by_name(...)`。
- 提炼：摘取图像编码函数时必须追踪生成程序中的外部名字、初始化顺序和宿主资源 API。单文件中的未声明名字是需核对的条件，不能直接断言整个库运行失败，也不能假定别的扩展一定会补上。
- 反例：编码函数将图像保存成 JPEG，但帧转换的 data URL 前缀写为 `data:image/png;base64,`。复用时应使数据 MIME 与实际编码一致，不能因为仓库公开就照抄此组合。此处是源码中的格式不一致，未测试具体消费者表现。
- 验证范围：仅源码观察。标准库、环境内置库和需要安装的第三方包分别处理，不能从 import 自动推断 requirements；迁移依赖时遵循 [Python 模式指南](python-block-mode.md) 的来源要求。
- 原始文件 SHA-256：`func.js` 为 `5821b329a1f63a024230cdc292b81299b961715717244b83cf76c87f6eba0ac8`。
