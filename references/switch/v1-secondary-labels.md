# V1 二级标签文字转 V2 二级菜单

V1 字段依据：[官方扩展 API 的“二级标签文字”](https://mindplus.dfrobot.com.cn/ext-api)，2026-09-14 核对。官方定义是 `blockType="tag"`，显示文字由 `block` 提供，对应导出函数应为空且名称不重复。以下 V2 菜单映射是本 Skill 的转换约定，不把 V1 标签函数当成功能函数。

## 转换示例

V1 声明：

```typescript
//% block="校准" blockType="tag"
export function calibrationLabel() {}
```

V2 在 blocks 中声明菜单（假设扩展 id 为 sensor）：

```javascript
{
    blockType: BlockType.SUBMENU,
    id: 'sensorCalibration',
    text: formatMessage({id: 'sensor.submenu.calibration', default: '校准'})
}
```

属于校准组的真实积木添加 `submenuId: 'sensorCalibration'`；保留这些积木原有 opcode、参数和 func 行为。标签自身不生成 opcode 或 func 方法。

## 归属与边界

- 清单的 `v1_entry_inventory.<mode>.secondary_labels` 记录标签文字、函数名、源码行号及是否空函数，并触发 `shared.block.special` Topic。可确认的空标签函数从真实功能函数对账集合移除。
- 按源码顺序、已有展示及上下文核对标签下的成员；下一个标签是分组候选边界，但 V1 文档没有声明成员字段，不把顺序猜测当作已确认归属。归属不清时只确认这一处，不将后续所有积木盲目塞入菜单。
- 无标签的普通积木保留在主分类。转换时已有标签是明确的布局依据，可转换为二级菜单；“新建库仅为校准等高级用法额外建菜单”的默认设计规则，不应导致删除 V1 已有分组。
- 菜单实体 id 按扩展 id 加驼峰用途名生成，翻译 message ID 单独设置；保留有依据的原文与翻译，按 V2 要求处理菜单文字中的不允许字符。重复标签文字不代表同一组，实体 id 必须唯一。
- `block="---"` 是空行，映射为 V2 分隔符，不是 SUBMENU；参数下拉菜单也不是二级菜单。
- 标签函数非空、注释不完整或语法超出清单提取范围时，保留源码并人工核对，不删除可能有行为的代码、不宣称自动迁移完成。不要把该函数仅改成无行为菜单。

完成后核对菜单声明与成员引用、翻译键、真实 opcode／func 对账；没有运行 Mind+ 时只报告源码核查结果。V2 机制见 [积木组织规范](block-organization.md)。
