import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "switch"))
from spec_to_inventory import build_inventory, SpecError
from select_reference_topics import select
from create_config_skeleton import build_config
from check_converted_extension import check_config_schema, check_python_requirements


class AdditionalModeTests(unittest.TestCase):
    def spec(self, mode, stage=False):
        value = {"identity": {"id": "demo", "author": "Tester", "version": "1.0.0"},
                 "mode": mode, "blocks": [{"opcode": "read", "parameters": [],
                 "generator_claim": "return this.device.firmata.digitalRead(args.PIN)" if mode == "REALTIME"
                 else "generator.addImport('import time'); generator.getSetup('timer'); return code"}],
                 "dependencies": [], "devices": [{"id": "dev-DFRobot-unihikerK10", "version": "^0.0.1"}]}
        if mode == "REALTIME":
            value["is_support_stage"] = stage
            if stage:
                value["devices"] = []
                value["blocks"][0]["generator_claim"] = "return runtime.getDevice()"
        return value

    def inventory(self, folder, spec):
        path = folder / "spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return build_inventory(spec, path, None)

    def config(self, mode):
        schema = json.loads((ROOT / "references/switch/config-schema.json").read_text())
        return build_config({"author": "Tester", "version": "1.0.0",
                             "name": {"en": "Demo", "zh-cn": "Demo"},
                             "description": {"en": "Demo", "zh-cn": "Demo"}},
                            {"identity": {"canonical_v2_id": "demo", "expected_compatibility_id": ""}}, mode, schema)

    def test_new_mode_topic_selection_uses_mode_specific_apis(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for mode, stage in [("MICROPYTHON", False), ("REALTIME", False), ("REALTIME", True)]:
                with self.subTest(mode=mode, stage=stage):
                    inventory = self.inventory(folder, self.spec(mode, stage))
                    path = folder / "inventory.json"
                    path.write_text(json.dumps(inventory), encoding="utf-8")
                    result = select(path, ROOT / "references/switch/generated", mode)
                    ids = {x["topic_id"] for x in result["topics"]}
                    self.assertIn("micropython.generator.get-setup" if mode == "MICROPYTHON"
                                  else "realtime.stage" if stage else "realtime.firmata", ids)
                    self.assertFalse(any(x.startswith(("upload.", "python.")) for x in ids))

    def test_device_scope_and_stage_spec_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("MICROPYTHON", "REALTIME"):
                value = self.spec(mode)
                value["devices"] = []
                with self.assertRaises(SpecError):
                    self.inventory(Path(directory), value)
            value = self.spec("REALTIME", True)
            value["devices"] = [{"id": "dev-DFRobot-unihikerK10"}]
            with self.assertRaises(SpecError):
                self.inventory(Path(directory), value)

    def test_config_profiles_and_realtime_conditional_devices(self):
        for mode in ("UPLOAD", "PYTHON_BLOCK", "MICROPYTHON", "REALTIME"):
            with self.subTest(mode=mode):
                config = self.config(mode)
                if mode in {"MICROPYTHON", "REALTIME"}:
                    config["supportDevices"] = {"dev-DFRobot-unihikerK10": "^0.0.1"}
                findings = []
                check_config_schema(config, mode, findings)
                self.assertEqual(findings, [])
        config = self.config("REALTIME")
        findings = []
        check_config_schema(config, "REALTIME", findings)
        self.assertIn("V2_CONFIG_REQUIRED_FIELDS_MISSING", {x["code"] for x in findings})
        config["isSupportStage"] = True
        findings = []
        check_config_schema(config, "REALTIME", findings)
        self.assertEqual(findings, [])
        config["supportDevices"] = {"dev-DFRobot-unihikerK10": "^0.0.1"}
        findings = []
        check_config_schema(config, "REALTIME", findings)
        self.assertIn("REALTIME_STAGE_SUPPORT_DEVICES_FORBIDDEN", {x["code"] for x in findings})

    def test_micropython_requirements_preserve_exact_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            spec = self.spec("MICROPYTHON")
            spec["dependencies"] = [{"requirement": "sensor-lib==1.2.3"}]
            inventory = self.inventory(folder, spec)
            findings = []
            check_python_requirements(folder, inventory, findings, "MICROPYTHON")
            self.assertEqual(findings[0]["code"], "V2_MICROPYTHON_REQUIREMENTS_MISSING")
            (folder / "public").mkdir()
            (folder / "public/requirements.txt").write_text("sensor-lib==1.2.3\n")
            findings = []
            check_python_requirements(folder, inventory, findings, "MICROPYTHON")
            self.assertEqual(findings, [])

    def test_checker_cli_accepts_new_modes_and_detects_wrong_execution_model(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            extension = folder / "extension"
            for subdir in ("public", "icon", "locales"):
                (extension / subdir).mkdir(parents=True)
            (extension / "icon/blockIcon.svg").write_text('<svg fill="#ffffff"/>')
            (extension / "icon/menuIcon.svg").write_text('<svg fill="#00b0f0"/>')
            for locale in ("en", "zh-cn"):
                (extension / f"locales/{locale}.json").write_text('{"demo.read":"Read"}')
            for mode in ("MICROPYTHON", "REALTIME"):
                with self.subTest(mode=mode):
                    inventory = self.inventory(folder, self.spec(mode))
                    (folder / "inventory.json").write_text(json.dumps(inventory))
                    config = self.config(mode)
                    config["supportDevices"] = {"dev-DFRobot-unihikerK10": "^0.0.1"}
                    (extension / "public/config.json").write_text(json.dumps(config))
                    primitive = "getPrimitives" if mode == "REALTIME" else "getCodePrimitives"
                    (extension / "index.js").write_text("class Extension { " + primitive + "() { return this.funcs; } getInfo() { return {"
                        "color1:'#00b0f0',color2:'#0099cc',color3:'#007799', blocks:[{opcode:'read',text:formatMessage({id:'demo.read'})}]}; }}")
                    (extension / "func.js").write_text("class Func {\n  async read(args, util) { return 1; }\n}" if mode == "REALTIME"
                        else "class Func {\n  read(generator, block, parameter) { generator.addWhile('poll', 'poll()', true); return ['value', generator.ORDER_ATOMIC]; }\n}")
                    args = [sys.executable, "-X", "utf8", str(ROOT / "scripts/switch/check_converted_extension.py"),
                            "--project-root", str(folder), "--inventory", str(folder / "inventory.json"), "--mode", mode]
                    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    (extension / "func.js").write_text("class Func {\n  read(generator, block, parameter) { generator.addCode('x'); }\n}")
                    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
                    codes = {x["code"] for x in json.loads(result.stdout)["findings"]}
                    self.assertIn("REALTIME_USES_CODE_GENERATOR" if mode == "REALTIME" else "MICROPYTHON_USES_UPLOAD_ADD_CODE", codes)


if __name__ == "__main__":
    unittest.main()
