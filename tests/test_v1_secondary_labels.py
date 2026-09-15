import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "switch"))
from inventory_v1 import entry_inventory
from check_converted_extension import collect_submenus

class SecondaryLabelTests(unittest.TestCase):
    def test_empty_tags_are_layout_not_functions(self):
        source = """//% block="Read" blockType="reporter"
export function readValue() { return 1; }
//% block="Calibration"
//% blockType="tag"
export function calibrationLabel() {}
//% block="Advanced" blockType="tag"
export function unsafeLabel() { doSomething(); }
//% block="---"
export function separator() {}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.ts"
            path.write_text(source)
            for mode in ("UPLOAD", "PYTHON_BLOCK"):
                result = entry_inventory({mode: path})[mode]
                self.assertNotIn("calibrationLabel", result["block_functions"])
                self.assertIn("readValue", result["block_functions"])
                self.assertIn("unsafeLabel", result["block_functions"])
                self.assertEqual(len(result["secondary_labels"]), 2)
                self.assertEqual(result["secondary_labels"][0]["text"], "Calibration")
                self.assertFalse(result["secondary_labels"][1]["empty_body"])


SUBMENU_INDEX = """getInfo() {
    return {
        blocks: [
            {
                blockType: BlockType.SUBMENU,
                id: 'sensorCalibration',
                text: formatMessage({id: 'gui.blocklyText.sensor.submenu.calibration', default: '校准'})
            },
            {
                opcode: 'setCalibrationTemperature',
                submenuId: 'sensorCalibration',
                blockType: BlockType.COMMAND,
                text: formatMessage({id: 'gui.blocklyText.sensor.setCalibrationTemperature', default: '设置校准温度 [TEMP]'}),
                arguments: {TEMP: {type: ArgumentType.NUMBER, defaultValue: 25}}
            },
            {
                opcode: 'readValue',
                blockType: BlockType.REPORTER,
                text: formatMessage({id: 'gui.blocklyText.sensor.readValue', default: '读取传感器数值'})
            }
        ]
    };
}
"""


class SubmenuEntityIdTests(unittest.TestCase):
    """二级菜单实体 id 不是翻译键，不能被要求出现在 locales 中。"""

    def test_entity_id_is_split_from_message_ids(self):
        declared, referenced = collect_submenus(SUBMENU_INDEX)
        self.assertEqual(set(declared), {"sensorCalibration"})
        self.assertEqual(referenced, {"sensorCalibration"})
        # 实体 id 只出现在 SUBMENU 声明里，声明对象自身没有 opcode
        self.assertNotIn("opcode", declared["sensorCalibration"])
        # formatMessage 的翻译 id 不是实体 id
        self.assertNotIn("gui.blocklyText.sensor.submenu.calibration", declared)

    def test_message_id_regex_still_finds_format_message_ids(self):
        import re
        literal_ids = set(re.findall(r"\bid\s*:\s*['\"]([^'\"]+)['\"]", SUBMENU_INDEX))
        self.assertIn("sensorCalibration", literal_ids)
        declared, _ = collect_submenus(SUBMENU_INDEX)
        remaining = literal_ids - set(declared)
        self.assertNotIn("sensorCalibration", remaining)
        self.assertEqual(
            remaining,
            {
                "gui.blocklyText.sensor.submenu.calibration",
                "gui.blocklyText.sensor.setCalibrationTemperature",
                "gui.blocklyText.sensor.readValue",
            },
        )

    def test_empty_index_has_no_submenus(self):
        declared, referenced = collect_submenus("getInfo() { return { blocks: [] }; }")
        self.assertEqual(declared, {})
        self.assertEqual(referenced, set())
