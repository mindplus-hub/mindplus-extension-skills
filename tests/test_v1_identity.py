"""旧包身份（compatibilityId）的发现与派生。

回归背景：V1 源有两种布局——包在源目录内，或与源目录并列。只查目录内部时，
`djkj-esp8266-iot-thirdex-V0.0.1/`（解压目录）会漏掉同级的
`djkj-esp8266-iot-thirdex-V0.0.1.mpext`，于是退化成按 author/id 拼身份；而 V1 身份不含
空白（id `ESP8266 IOT` 对应包名 `esp8266-iot`），保留空格会得到无法匹配的 compatibilityId。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "switch"
sys.path.insert(0, str(SCRIPTS))
from inventory_v1 import (  # noqa: E402
    config_package_identity,
    legacy_package_identities,
    normalize_identity_text,
)


V1_CONFIG = {
    "name": {"zh-cn": "示例", "en": "Demo"},
    "author": "DJKJ",
    "id": "ESP8266 IOT",
    "version": "0.0.1",
    "asset": {"arduinoC": {"dir": "arduinoC/", "version": "0.0.1", "board": ["esp8266"], "main": "main.ts"}},
}


def write_source(root: Path, name: str = "djkj-esp8266-iot-thirdex-V0.0.1") -> Path:
    source = root / name
    (source / "arduinoC").mkdir(parents=True)
    (source / "config.json").write_text(json.dumps(V1_CONFIG, ensure_ascii=False), encoding="utf-8")
    (source / "arduinoC" / "main.ts").write_text(
        '//% block="led on" blockType="command"\nexport function ledOn(parameter: any, block: any) {}\n',
        encoding="utf-8",
    )
    return source


class IdentityTextTests(unittest.TestCase):
    def test_whitespace_becomes_hyphen_and_lowercases(self):
        self.assertEqual(normalize_identity_text("ESP8266 IOT"), "esp8266-iot")
        self.assertEqual(normalize_identity_text("FM_RADIO "), "fm_radio-")
        # 下划线、中文、括号等原始字符保留
        self.assertEqual(normalize_identity_text("yfrobot_legoduino"), "yfrobot_legoduino")
        self.assertEqual(normalize_identity_text("铁熊"), "铁熊")

    def test_config_package_identity(self):
        self.assertEqual(config_package_identity(V1_CONFIG), "djkj-esp8266-iot-thirdex")
        self.assertIsNone(config_package_identity({"author": "x"}))
        self.assertIsNone(config_package_identity(None))


class PackageDiscoveryTests(unittest.TestCase):
    def test_sibling_package_beside_extracted_folder_is_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_source(root)
            (root / "djkj-esp8266-iot-thirdex-V0.0.1.mpext").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            self.assertEqual(legacy_package_identities(source), ["djkj-esp8266-iot-thirdex"])

    def test_package_inside_source_folder_is_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_source(root)
            (source / "djkj-esp8266-iot-thirdex-V0.0.1.mpext").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            self.assertEqual(legacy_package_identities(source), ["djkj-esp8266-iot-thirdex"])

    def test_unrelated_sibling_package_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_source(root)
            (root / "lihomqtt-mqttcenter-thirdex-V0.0.1.mpext").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            self.assertEqual(legacy_package_identities(source), [])

    def test_two_packages_inside_one_source_are_both_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_source(root)
            for version in ("V0.0.1", "V0.0.2"):
                (source / f"djkj-esp8266-iot-thirdex-{version}.mpext").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            self.assertEqual(legacy_package_identities(source), ["djkj-esp8266-iot-thirdex"])


class InventoryIdentityTests(unittest.TestCase):
    def run_inventory(self, source: Path, out: Path) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "inventory_v1.py"), "--source", str(source), "--output", str(out)],
            capture_output=True, encoding="utf-8", check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_sibling_package_proves_identity_and_avoids_false_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_source(root)
            (root / "djkj-esp8266-iot-thirdex-V0.0.1.mpext").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            result = self.run_inventory(source, root / "inventory.json")
            identity = result["identity"]
            self.assertEqual(identity["legacy_package_identities"], ["djkj-esp8266-iot-thirdex"])
            self.assertEqual(identity["expected_compatibility_id"], "djkj-esp8266-iot-thirdex")
            self.assertEqual(identity["compatibility_evidence"], "mpext_filename")
            codes = {finding["code"] for finding in result["source_anomalies"]}
            self.assertNotIn("LEGACY_PACKAGE_CONFIG_IDENTITY_CONFLICT", codes)

    def test_fallback_without_package_normalizes_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_source(root)
            result = self.run_inventory(source, root / "inventory.json")
            identity = result["identity"]
            self.assertEqual(identity["legacy_package_identities"], [])
            self.assertEqual(identity["expected_compatibility_id"], "djkj-esp8266-iot-thirdex")
            self.assertEqual(identity["compatibility_evidence"], "config_author_id")
            codes = {finding["code"] for finding in result["source_anomalies"]}
            self.assertNotIn("LEGACY_PACKAGE_CONFIG_IDENTITY_CONFLICT", codes)


if __name__ == "__main__":
    unittest.main()
