import json
import sys
import tempfile
import unittest
from pathlib import Path
from test_workflow import sample_spec

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "switch"))
from spec_to_inventory import build_inventory, SpecError


class AuthorIdentityTests(unittest.TestCase):
    def test_frozen_creation_spec_requires_normalized_author(self):
        for author in ("LiMing", "ZhangSan", "DFRobot", "MindPlus", "Li Ming_01", "张三", "123", ""):
            with self.subTest(author=author), tempfile.TemporaryDirectory() as tmp:
                spec = sample_spec()
                spec["identity"]["author"] = author
                path = Path(tmp) / "spec.json"
                path.write_text(json.dumps(spec), encoding="utf-8")
                if author in ("LiMing", "ZhangSan", "DFRobot", "MindPlus"):
                    build_inventory(spec, path, None)
                else:
                    with self.assertRaises(SpecError):
                        build_inventory(spec, path, None)
                self.assertEqual(spec["identity"]["author"], author)

    def test_new_project_compatibility_defaults_to_empty(self):
        for value in (None, "", "legacy-demo-thirdex", "MISSING"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                spec = sample_spec()
                if value == "MISSING":
                    spec["identity"].pop("compatibility_id")
                else:
                    spec["identity"]["compatibility_id"] = value
                path = Path(tmp) / "spec.json"
                path.write_text(json.dumps(spec), encoding="utf-8")
                result = build_inventory(spec, path, None)
                self.assertEqual(result["identity"]["expected_compatibility_id"], "legacy-demo-thirdex" if value == "legacy-demo-thirdex" else "")
