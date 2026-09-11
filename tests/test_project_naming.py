from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "switch"))
from route_workflow import route, read_json, REGISTRY_PATH
from prepare_builder_scaffold import validate_target, ScaffoldError


class ProjectNamingTests(unittest.TestCase):
    def test_fresh_routes_and_scaffold_agree(self):
        registry = read_json(REGISTRY_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            source.mkdir()
            for goal in ("CREATE", "CONVERT"):
                for name in ("sensor", "ext-sensor", "EXT2-sensor", "ext2-", "ext2-sensor"):
                    with self.subTest(goal=goal, name=name):
                        project = base / name
                        request = {"goals": [goal], "paths": {"project_root": str(project), "v1_source": str(source)}, "authorizations": {"local_write": True}}
                        result = route(request, registry)
                        if name == "ext2-sensor":
                            self.assertEqual(result["status"], "PASS")
                            validate_target(project)
                        else:
                            self.assertEqual(result["reason_code"], "WORKSPACE.PROJECT_NAME_PREFIX_REQUIRED")
                            with self.assertRaises(ScaffoldError):
                                validate_target(project)
                        self.assertFalse(project.exists())
                        self.assertEqual(request["paths"]["project_root"], str(project))

    def test_existing_projects_keep_their_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "legacy-name"
            project.mkdir()
            (project / "config.json").write_text("{}")
            for goal in ("UPGRADE", "REVIEW", "PUBLISH"):
                with self.subTest(goal=goal):
                    result = route({"goals": [goal], "paths": {"project_root": str(project)}, "authorizations": {"local_write": True, "commit": True, "push": True}}, read_json(REGISTRY_PATH))
                    self.assertEqual(result["status"], "PASS")
                    self.assertEqual(result["facts"]["project_root"], str(project.resolve()))


if __name__ == "__main__":
    unittest.main()
