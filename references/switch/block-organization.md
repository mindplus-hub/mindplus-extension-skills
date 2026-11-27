# 积木组织模式（block organization）

CREATE 设计积木时使用；UPGRADE 仅对本次新增或明确要求重组的部分使用。CONVERT 优先保留原有 opcode、参数、菜单值和生成语义，不能为减少积木数量擅自合并旧接口。

V1 转换的已有 `blockType="tag"` 按 [二级标签映射](v1-secondary-labels.md) 保留为菜单分组；下述普通／高级布局是新建设计默认，不覆盖来源已有分组。

默认布局：普通积木直接显示在扩展主分类，不设置二级菜单；只有校准等高级用法才额外建立二级菜单，并仅将相关高级积木放入。没有高级功能就不声明 SUBMENU。机制约束以内置官方 Topic 为准。

## 积木设计与分组

- 先整理用户操作顺序：初始化／连接 → 配置 → 执行／刷新 → 读取／判断；根层级优先露出最常用的操作。没有必要的初始化就不额外造一个。
- 执行动作用 COMMAND，返回数据用 REPORTER，条件判断用 BOOLEAN；HAT 仅用于当前模式确实支持且有事件实现的入口，不把轮询命令仅改外形就当作事件。模式与输出类型按对应 Topic 校验。
- 同一操作、相同参数结构和相同结果类型的离散选项可用下拉合并，例如读取温度／气压／海拔，或读取年月日时分秒。单位随选项不同的，应在选项文字或说明中明确。
- 参数结构、返回类型、执行条件或副作用不同的功能不为了压缩数量硬合并。例如 I2C 与 UART 初始化参数不同可分开；“刷新检测结果”和“获取某项数据”应让用户看得出调用顺序。
- 文案说明动作、对象、参数含义及必要单位；`[PARAM]` 与 arguments 的键一致。下拉显示文字本地化，内部 value 稳定，不以翻译文本代替代码值。默认值应存在于对应菜单中，并与实际生成代码一致。
- 普通积木无论数量多少都留在主分类，可用合理顺序和下拉参数减少重复。只有校准、校准值复位、诊断等高级操作才放入对应二级菜单；不为普通设置和普通读数分别创建菜单，不按 COMMAND／REPORTER 外形分组。
- 初始化、连接、常用配置、日常读取和判断直接放在主分类；二级菜单使用“校准”等明确的高级用途名称，不把基本使用步骤藏入其中。

## 机制一：子目录（SUBMENU）

Mind+ 通过 `BlockType.SUBMENU` 声明"子目录"，高级积木用 `submenuId` 挂进去：

```javascript
// getInfo() 返回对象中的 blocks；扩展 id 为 sensor
blocks: [
    // 普通读数：不写 submenuId，直接显示在扩展主分类
    {
        opcode: 'readValue',
        blockType: BlockType.REPORTER,
        text: formatMessage({id: 'sensor.readValue', default: '读取传感器数值'})
    },
    // 只有存在高级操作时才声明此二级菜单
    {
        blockType: BlockType.SUBMENU,
        id: 'sensorCalibration',
        text: formatMessage({id: 'sensor.submenu.calibration', default: '校准'})
    },
    {
        opcode: 'setCalibrationTemperature',
        blockType: BlockType.COMMAND,
        submenuId: 'sensorCalibration',
        text: formatMessage({
            id: 'sensor.setCalibrationTemperature',
            default: '设置校准温度 [TEMP] °C'
        }),
        arguments: {TEMP: {type: ArgumentType.NUMBER, defaultValue: 25}}
    },
    {
        opcode: 'resetCalibration',
        blockType: BlockType.COMMAND,
        submenuId: 'sensorCalibration',
        text: formatMessage({id: 'sensor.resetCalibration', default: '恢复默认校准值'})
    }
]

```

要点（前两条为官方规范，见 generated 的 `shared.block.special`）：

- **子目录 `id` 必须采用驼峰命名**：扩展库 `id` + 子目录名称首字母大写后拼接。
  例如扩展库 `test` 的 `menu1` 子目录，`id` 必须写为 `testMenu1`。
- **二级菜单的翻译文字不得包含特殊字符**（引号、`&`、`<`、`>` 等），否则积木无法显示。
- `id` 与翻译 message ID 分开：新建菜单用如 `sensorCalibration` 的实体 ID，翻译可用 `gui.blocklyText.sensor.submenu.calibration`。不要把翻译 ID 当作实体菜单 ID。
- 每个 `submenuId` 必须引用实际声明且唯一的 SUBMENU `id`；不要自行增加三级嵌套字段。下拉 `menus` 是参数选项，与二级菜单不是同一机制。
- 子目录声明自身**没有 opcode、没有 func.js 方法**，只有 `id`（子目录标识）和 `text`。
- 不写 `submenuId` 的积木留在扩展根层级；初始化等普通积木不填写该字段。

### 显示效果示例

扩展主分类直接显示“读取模拟引脚的电导率”等日常积木；分类下额外显示“校准”入口。点击“校准”后展示校准温度、标准液校准、恢复默认校准值、读取校准系数、读取校准用原始电压等高级积木。某项操作属于普通还是高级，按用户用途判断，不按积木外形判断。

上方代码仅展示组织方式；实际项目仍需实现对应 func 方法、参数处理及各语言翻译。

## 机制二：下拉参数合并同构积木

一个功能有多个离散取值时，用下拉参数代替一族积木：

```javascript
arguments: {
    ADDR: {
        type: ArgumentType.STRING,
        menu: 'commMenu',        // 指向 menus 里声明的菜单
        defaultValue: '0x2A'
    }
}
```

菜单本身在 index.js 的 menus 区声明（选项列表 + 每项的 message ID），
机制细节读 generated 主题 `shared.block.menus` 与 `fields/dropdown`。

## 何时用哪个（决策规则）

| 情形 | 做法 |
| --- | --- |
| 同一操作有 N 个离散取值（地址、模式、量程） | 一个积木 + 下拉参数 |
| 普通初始化、设置、执行、读取、判断 | 直接放主分类，不设二级菜单 |
| 校准等高级操作 | 额外建立对应 SUBMENU，只收入相关高级积木 |
| 取值来自设备动态枚举 | 动态菜单（dynamic-menu，generated 主题） |

积木较多不构成新增二级菜单的理由；先调整顺序并评估同构操作的下拉合并。
在 spec 的 blocks 结构记录分组决定（每个 block 标注所属 submenu）；根层级不填 submenu。

## 校验联动

- 子目录声明没有 func 方法是正常的；`check_converted_extension.py` 的
  opcode/func 对账只针对真实积木（spec blocks 列表）。
- 合并后 spec 里每个积木的 `parameters[].field`（如 `dropdown`）会驱动
  `select_reference_topics.py` 选中 `field-dropdown` 等主题。

## 检查与问题分级

按 [issue-levels.md](../issue-levels.md) 结合实际影响定级：分组、顺序、命名风格通常是 P1 建议；已导致积木无法显示、参数或生成器映射断裂的问题是 P0。记录菜单声明及成员归属、翻译键、占位符与参数键、默认值与菜单值、真实 opcode 与 func 方法的对应关系。没有实际运行 Mind+ 时，只报告源码已核查，不宣称二级菜单显示正常。

调整布局时不顺便改 opcode、参数键、旧菜单值或兼容身份；确需改变行为，应纳入本次功能与回归范围。
