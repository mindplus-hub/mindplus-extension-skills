# 积木组织模式（block organization）

CREATE 从零设计积木清单时的组织参考。证据来源：`DFRobot_C4001` 毫米波扩展
（用户已验证的正式扩展，22 个功能经子目录 + 下拉合并收敛为 9 个积木 + 2 个子菜单）。
CONVERT 保持 V1 原有组织结构，本文件仅用于 V1 结构含糊时的对齐参考。

## 机制一：子目录（SUBMENU）

Mind+ 通过 `BlockType.SUBMENU` 声明"子目录"，普通积木用 `submenuId` 挂进去：

```javascript
// 1) 先声明子目录（与积木平级，无 opcode）
{
    blockType: BlockType.SUBMENU,
    id: '<extId>Menu1',          // 官方命名规则：扩展库 id + 子目录名首字母大写拼接
    text: formatMessage({
        id: 'gui.blocklyText.<extId>.submenu.menu1',
        default: '设置'
    })
},
// 2) 成员积木通过 submenuId 归入子目录
{
    opcode: 'setSensorMode',
    text: formatMessage({
        id: 'gui.blocklyText.<extId>.setSensorMode',
        default: '设置传感器模式为 [MODE]'
    }),
    blockType: BlockType.COMMAND,
    submenuId: '<extId>Menu1',
    arguments: { ... }
}
```

要点（前两条为官方规范，见 generated 的 `shared.block.special`）：

- **子目录 `id` 必须采用驼峰命名**：扩展库 `id` + 子目录名称首字母大写后拼接。
  例如扩展库 `test` 的 `menu1` 子目录，`id` 必须写为 `testMenu1`。
  （历史项目 C4001 用了纯小写 `setmodel`，属于旧式写法，新扩展遵循官方规则。）
- **二级菜单的翻译文字不得包含特殊字符**（引号、`&`、`<`、`>` 等），否则积木无法显示。
- 子目录声明自身**没有 opcode、没有 func.js 方法**，只有 `id`（子目录标识）和 `text`。
- 不写 `submenuId` 的积木留在扩展根层级；初始化积木（如 `initRadar`）通常留在根层级。

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
| 功能可分成清晰的组（设置类 / 读数类） | SUBMENU 子目录 |
| 初始化积木 | 留根层级 |
| 取值来自设备动态枚举 | 动态菜单（dynamic-menu，generated 主题） |

超过 ~10 个积木的清单应先做一轮"下拉合并 + 子目录分组"再实现，
并把分组决定记入 spec 的 blocks 结构（每个 block 标注所属 submenu）。

## 校验联动

- 子目录声明没有 func 方法是正常的；`check_converted_extension.py` 的
  opcode/func 对账只针对真实积木（spec blocks 列表）。
- 合并后 spec 里每个积木的 `parameters[].field`（如 `dropdown`）会驱动
  `select_reference_topics.py` 选中 `field-dropdown` 等主题。
