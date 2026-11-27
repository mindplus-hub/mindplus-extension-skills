import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/switch"))
from inventory_v1 import mode_entries
from select_reference_topics import select, SelectionError
from create_config_skeleton import build_config


def run(script, *args):
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/switch" / script), *map(str, args)],
                            capture_output=True, text=True, encoding="utf-8")
    return result, json.loads(result.stdout)


class V1AdditionalModeTests(unittest.TestCase):
    def source(self, base, mode, custom=False):
        source = base / "v1"
        source.mkdir()
        language = "micropython" if mode == "MICROPYTHON" else "javascript"
        directory = "src/blocks" if custom else language
        folder = source / directory
        folder.mkdir(parents=True)
        main = "main.ts" if mode == "MICROPYTHON" else "main.js"
        asset = {"dir": directory, "main": main, "board": ["esp32"]}
        config = {"id": "Demo_V1", "author": "Tester", "version": "1.2.3", "asset": {language: asset}}
        if mode == "MICROPYTHON":
            asset["dependencies"] = {"sensorlib": "==1.2.0"}
            (folder / "main.ts").write_text('''//% color="#00b0f0"
namespace demo {
//% block="read [PIN]" blockType="reporter"
//% PIN.shadow="number" PIN.defl="2"
export function read(parameter: any, block: any) {
    Generator.addImport("sensor", "import sensor");
    Generator.getSetup("sensor");
    Generator.addCode("sensor.read(" + parameter.PIN.code + ")");
}
}
''')
            (folder / "libraries").mkdir()
            (folder / "libraries/requirements.txt").write_text("driver==2.0\n")
            (folder / "libraries/sensor.py").write_text("def read(pin):\n    return pin + 1\n")
        else:
            (folder / "index.js").write_text('''class OldExtension {
    constructor(runtime, id) { this.runtime = runtime; }
    getInfo() {
        return {color1: '#00b0f0', blocks: [
            {opcode: 'read', blockType: BlockType.REPORTER, text: 'read [PIN]', arguments: {PIN: {defaultValue: 2}}},
            {opcode: 'wait', blockType: BlockType.COMMAND, text: 'wait'},
            {opcode: 'whenReady', blockType: BlockType.HAT, text: 'when ready'}
        ], menus: {pins: {items: 'getPins'}}};
    }
    async read(args, util) { return this.runtime.getDevice().firmata.digitalRead(args.PIN); }
    wait(args, util) { util.yield(); }
    whenReady(args) { return true; }
}
module.exports = OldExtension;
''')
        (source / "config.json").write_text(json.dumps(config))
        return source

    def test_v1_inventory_selection_and_source_integrity(self):
        for mode in ("MICROPYTHON", "REALTIME"):
            for custom in (False, True):
                with self.subTest(mode=mode, custom=custom), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    source = self.source(base, mode, custom)
                    initial = base / "initial.json"
                    process, inventory = run("inventory_v1.py", "--source", source, "--output", initial)
                    self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                    self.assertEqual([x["mode"] for x in inventory["candidates"]], [mode])
                    facts = inventory["v1_entry_inventory"][mode]
                    self.assertIn("read", facts["block_functions"])
                    self.assertEqual(facts["declared_color1"], "#00b0f0")
                    selection = select(initial, ROOT / "references/switch/generated", mode)
                    ids = {x["topic_id"] for x in selection["topics"]}
                    if mode == "MICROPYTHON":
                        self.assertEqual(inventory["micropython_dependency_inventory"]["expected_requirement_lines"],
                                         ["sensorlib==1.2.0", "driver==2.0"])
                        self.assertEqual(inventory["python_dependency_inventory"]["expected_requirement_lines"], [])
                        self.assertIn("micropython.generator.get-setup", ids)
                    else:
                        self.assertEqual(facts["block_functions"], ["read", "wait", "whenReady"])
                        self.assertIn("read", facts["execution_methods"])
                        self.assertIn("realtime.firmata", ids)
                        self.assertIn("shared.block.menus", ids)
                    current = base / "current.json"
                    run("inventory_v1.py", "--source", source, "--output", current)
                    process, compared = run("compare_inventory.py", "--initial", initial, "--current", current)
                    self.assertEqual(process.returncode, 0, compared)
                    entry = Path(facts["entry"])
                    entry.write_text(entry.read_text() + "\n// changed\n")
                    run("inventory_v1.py", "--source", source, "--output", current)
                    process, compared = run("compare_inventory.py", "--initial", initial, "--current", current)
                    self.assertEqual(compared["reason_code"], "SOURCE_DRIFT")

    def test_multiple_modes_require_selection_and_wrong_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = self.source(base, "MICROPYTHON")
            (source / "python").mkdir()
            (source / "python/main.ts").write_text("export function desktop() {}")
            initial = base / "initial.json"
            run("inventory_v1.py", "--source", source, "--output", initial)
            with self.assertRaises(SelectionError):
                select(initial, ROOT / "references/switch/generated", None)
            self.assertEqual(select(initial, ROOT / "references/switch/generated", "MICROPYTHON")["mode"], "MICROPYTHON")
            with self.assertRaises(SelectionError):
                select(initial, ROOT / "references/switch/generated", "REALTIME")

    def test_new_modes_can_initialize_and_resume_records(self):
        for mode, prefix in (("MICROPYTHON", "mpy"), ("REALTIME", "rt")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                source = self.source(base, mode)
                args = ("--work-root", base, "--v1-source", source, "--project-root", base / f"ext2-{prefix}-demo", "--mode", mode)
                process, record = run("init_run.py", *args)
                self.assertEqual(process.returncode, 0, record)
                self.assertIn(f"- mode: {mode}", (Path(record["run_root"]) / "log.md").read_text())

    def test_realtime_skeleton_keeps_explicit_stage_choice(self):
        schema = json.loads((ROOT / "references/switch/config-schema.json").read_text())
        inventory = {"identity": {"canonical_v2_id": "demo", "expected_compatibility_id": "tester-demo-thirdex"}}
        config = build_config({"isSupportStage": True}, inventory, "REALTIME", schema)
        self.assertIs(config["isSupportStage"], True)
        self.assertNotIn("supportDevices", config)
        self.assertEqual(config["compatibilityId"], "tester-demo-thirdex")

    def test_declared_entry_cannot_escape_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve()
            with self.assertRaises(ValueError):
                mode_entries(source, {"asset": {"micropython": {"dir": "../outside", "main": "main.ts"}}})


if __name__ == "__main__":
    unittest.main()
