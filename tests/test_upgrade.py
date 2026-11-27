import json
import tempfile
import unittest
from pathlib import Path

from test_workflow import run_script, lite_fixture
from route_workflow import route, read_json, REGISTRY_PATH
from hash_project import compute_project_hash
from validate_handoff import validate


class UpgradeTests(unittest.TestCase):
    def test_upgrade_route_gates_and_optional_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            request = {"goals": ["UPGRADE"], "paths": {"project_root": str(project)},
                       "authorizations": {"local_write": True, "commit": True, "push": True}}
            registry = read_json(REGISTRY_PATH)
            self.assertEqual(route(request, registry)["reason_code"], "WORKSPACE.EXISTING_PROJECT_REQUIRED")
            (project / "config.json").write_text('{"version":"1.0.0"}')
            for profile, expected in (("BASIC", ["UPGRADE_EXISTING", "REVIEW_EXISTING", "PUBLISH_GITEE"]),):
                request.update(goals=["UPGRADE", "PUBLISH"], review_profile=profile)
                self.assertEqual(route(request, registry)["workflows"], expected)
            for producer in ("CREATE", "CONVERT"):
                request["goals"] = ["UPGRADE", producer]
                self.assertEqual(route(request, registry)["reason_code"], "ROUTE.CONFLICTING_PRODUCERS")
            request["goals"] = ["UPGRADE"]
            request["authorizations"]["local_write"] = False
            self.assertEqual(route(request, registry)["reason_code"], "AUTH.LOCAL_WRITE_REQUIRED")
            request["goals"] = ["SYNC"]
            self.assertEqual(route(request, registry)["reason_code"], "ROUTE.UNSUPPORTED_EXISTING_V2_SYNC")

    def test_upgrade_binds_original_hash_and_advances_with_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "project"
            project.mkdir()
            config = project / "config.json"
            config.write_text('{"version":"1.0.0"}')
            original_hash = compute_project_hash(project)[0]
            start = ["mpa.py", "start", "--goals", "UPGRADE,PUBLISH", "--project-root", str(project),
                     "--work-root", str(base), "--run-id", "upgrade", "--auth", "local_write",
                     "--auth", "commit", "--auth", "push"]
            result = run_script(*start)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("upgrade.md", json.loads(result.stdout)["next_command"])
            config.write_text('{"version":"1.1.0","feature":true}')
            self.assertEqual(run_script(*start).returncode, 0)
            baseline = base / ".mindplus-agent/runs/upgrade/upgrade-baseline.json"
            self.assertEqual(json.loads(baseline.read_text())["sha256"], original_hash)
            args = ["mpa.py", "handoff", "--work-root", str(base), "--run-id", "upgrade",
                    "--workflow", "UPGRADE_EXISTING", "--status", "PASS", "--outcome", "UPGRADED"]
            self.assertNotEqual(run_script(*args).returncode, 0)
            for check in ("repository_ownership", "version_bump", "config_schema", "extension_static_integrity",
                          "source_semantics", "upgrade_regression"):
                args += ["--check", check + "=PASS", "--evidence", check + "=" + str(config)]
            args += ["--check", "lite_source_selection=PASS", "--evidence", "lite_source_selection=" + str(lite_fixture(project))]
            result = run_script(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            handoff = json.loads((base / ".mindplus-agent/runs/upgrade/handoffs/UPGRADE_EXISTING.json").read_text())
            self.assertEqual(handoff["input_provenance"]["sha256"], original_hash)
            self.assertNotEqual(handoff["project_sha256"], original_hash)
            self.assertEqual(validate(handoff, None, True), [])
            handoff.update(state="WAITING_USER", status="BLOCKED", outcome="TOKEN_REQUIRED",
                           reason_code="AUTH.GITEE_TOKEN_MISSING", checks=[], artifacts=[])
            self.assertEqual(validate(handoff, None, True), [])
            result = run_script("mpa.py", "transition", "--work-root", str(base), "--run-id", "upgrade")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["advanced_to"], "REVIEW_EXISTING")
            self.assertIn("review.md", json.loads(result.stdout)["next_command"])


if __name__ == "__main__":
    unittest.main()
