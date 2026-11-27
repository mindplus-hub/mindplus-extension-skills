import json
import tempfile
import unittest
from pathlib import Path
from test_workflow import run_script, run_switch_script

class UnifiedRecordsTests(unittest.TestCase):
    def test_parent_binding_idempotence_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "v1"
            source.mkdir()
            project = base / "ext2-ul-demo"
            start = run_script("mpa.py", "start", "--work-root", str(base), "--project-root", str(project), "--v1-source", str(source), "--goals", "CONVERT", "--run-id", "parent", "--auth", "local_write", "--keep-evidence")
            self.assertEqual(start.returncode, 0, start.stdout)
            self.assertIn("--parent-run-id", json.loads(start.stdout)["next_command"])
            args = ["--work-root", str(base), "--v1-source", str(source), "--project-root", str(project), "--parent-run-id", "parent"]
            first = run_switch_script("init_run.py", *args)
            self.assertEqual(first.returncode, 0, first.stdout)
            child = base / ".mindplus-agent/runs/parent/children/CONVERT_FRESH"
            self.assertEqual(Path(json.loads(first.stdout)["run_root"]), child)
            log = child / "log.md"
            log.write_text(log.read_text() + "checkpoint evidence\n")
            before = log.read_bytes()
            second = run_switch_script("init_run.py", *args)
            self.assertEqual(json.loads(second.stdout)["status"], "PASS_IDEMPOTENT")
            self.assertEqual(log.read_bytes(), before)
            conflict = run_switch_script("init_run.py", *args, "--mode", "UPLOAD")
            self.assertNotEqual(conflict.returncode, 0)
            self.assertEqual(log.read_bytes(), before)
            self.assertFalse((base / ".ms").exists())

    def test_standalone_uses_unified_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "v1"
            source.mkdir()
            result = run_switch_script("init_run.py", "--work-root", str(base), "--v1-source", str(source))
            self.assertEqual(result.returncode, 0, result.stdout)
            record = Path(json.loads(result.stdout)["run_root"])
            self.assertEqual(record.parent, base / ".mindplus-agent/conversions")
            self.assertTrue((record / "record.json").is_file())
            self.assertFalse((base / ".ms").exists())
