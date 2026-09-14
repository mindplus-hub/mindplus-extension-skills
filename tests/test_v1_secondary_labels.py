import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "switch"))
from inventory_v1 import entry_inventory

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
