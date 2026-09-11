import itertools
import json
import tempfile
import unittest
from pathlib import Path

from test_workflow import run_script, run_gitee, publish_fixture, FAKE_TOKEN, host_ready_handoff, write_json
from route_workflow import route, read_json, REGISTRY_PATH
from validate_handoff import validate
import gitee_publish as pub


class SimplifiedLifecycleTests(unittest.TestCase):
    def test_route_matrix_uses_only_requested_review(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "v1"
            source.mkdir()
            existing = base / "existing"
            existing.mkdir()
            (existing / "file").write_text("existing")
            external = base / "old-handoff.json"
            external.write_text("{}")
            for producer, review, publish, profile, old in itertools.product((None, "CREATE", "CONVERT"), (False, True), (False, True), ("BASIC", "HOST_READY"), (False, True)):
                goals = ([producer] if producer else []) + (["REVIEW"] if review else []) + (["PUBLISH"] if publish else [])
                if not goals:
                    continue
                with self.subTest(goals=goals, profile=profile, external=old):
                    request = {"goals": goals, "review_profile": profile,
                               "paths": {"project_root": str(base / "ext2-new" if producer else existing), "v1_source": str(source), "review_handoff": str(external) if old else None},
                               "authorizations": {"local_write": True, "commit": True, "push": True}}
                    result = route(request, read_json(REGISTRY_PATH))
                    expected = ([producer + "_FRESH"] if producer else []) + (["REVIEW_EXISTING"] if review or profile == "HOST_READY" else []) + (["PUBLISH_GITEE"] if publish else [])
                    self.assertEqual(result["workflows"], expected)

    def test_direct_publish_without_review_keeps_authorization_and_snapshot_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-project"
            project.mkdir()
            (project / "config.json").write_text("{}")
            pub.git(project, "init")
            pub.git(project, "config", "user.name", "Tester")
            pub.git(project, "config", "user.email", "tester@example.com")
            preflight = base / "preflight.json"
            import os
            env = dict(os.environ, GITEE_TOKEN=FAKE_TOKEN)
            common = ["prepare_gitee_publish.py", "--project-root", str(project), "--output", str(preflight)]
            blocked = run_script(*common, env=env)
            self.assertEqual(json.loads(blocked.stdout)["reason_code"], "AUTH.PUSH_NOT_AUTHORIZED")
            ready = run_script(*common, "--auth", "commit", "--auth", "push", env=env)
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertIsNone(json.loads(ready.stdout)["review_handoff"])
            for stage in (["plan"], ["commit", "--message", "Publish source"]):
                result = run_gitee(stage + ["--preflight", str(preflight), "--state-dir", str(base / "state")], {"GITEE_TOKEN": FAKE_TOKEN})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            (project / "config.json").write_text('{"changed":true}')
            stale = run_gitee(["plan", "--preflight", str(preflight), "--state-dir", str(base / "state")], {"GITEE_TOKEN": FAKE_TOKEN})
            self.assertNotEqual(stale.returncode, 0)

    def test_basic_review_passes_without_build_or_user_gui_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, _ = publish_fixture(Path(directory))
            handoff = host_ready_handoff(project)
            handoff["outcome"] = "REVIEWED_BASIC"
            handoff["checks"] = [{"id": name, "required": True, "result": "PASS", "evidence": [str(project)]} for name in ("config_schema", "extension_static_integrity", "source_semantics")]
            self.assertEqual(validate(handoff, None, True), [])
            handoff["checks"].pop()
            self.assertTrue(validate(handoff, None, True))

    def test_full_acceptance_is_not_satisfied_by_basic(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, _, _ = publish_fixture(base)
            start = run_script("mpa.py", "start", "--goals", "REVIEW", "--review-profile", "HOST_READY", "--project-root", str(project), "--work-root", str(base), "--run-id", "full")
            self.assertEqual(start.returncode, 0, start.stdout)
            args = ["mpa.py", "handoff", "--work-root", str(base), "--run-id", "full", "--workflow", "REVIEW_EXISTING", "--status", "PASS", "--outcome", "REVIEWED_BASIC"]
            for check in ("config_schema", "extension_static_integrity", "source_semantics"):
                args += ["--check", check + "=PASS", "--evidence", check + "=" + str(project)]
            result = run_script(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required outcome is REVIEWED_HOST_READY", result.stdout)
            # A hand-written BASIC result cannot bypass the profile at transition either.
            basic = host_ready_handoff(project)
            basic["outcome"] = "REVIEWED_BASIC"
            basic["checks"] = [{"id": name, "required": True, "result": "PASS", "evidence": [str(project)]} for name in ("config_schema", "extension_static_integrity", "source_semantics")]
            write_json(base / ".mindplus-agent/runs/full/handoffs/REVIEW_EXISTING.json", basic)
            result = run_script("mpa.py", "transition", "--work-root", str(base), "--run-id", "full")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required outcome is REVIEWED_HOST_READY", result.stdout)

    def test_created_project_goes_directly_to_publication_and_binds_late_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-new"
            start = run_script("mpa.py", "start", "--goals", "CREATE,PUBLISH", "--project-root", str(project), "--work-root", str(base), "--run-id", "new", "--auth", "local_write", "--auth", "commit", "--auth", "push")
            self.assertEqual(start.returncode, 0, start.stdout)
            run_root = base / ".mindplus-agent/runs/new"
            (run_root / "extension-spec.json").write_text("{}")
            project.mkdir()
            (project / "config.json").write_text("{}")
            handoff = run_script("mpa.py", "handoff", "--work-root", str(base), "--run-id", "new", "--workflow", "CREATE_FRESH", "--status", "PASS", "--outcome", "CREATED", "--check", "static=PASS", "--evidence", "static=" + str(project))
            self.assertEqual(handoff.returncode, 0, handoff.stdout)
            advanced = run_script("mpa.py", "transition", "--work-root", str(base), "--run-id", "new")
            result = json.loads(advanced.stdout)
            self.assertEqual(result["advanced_to"], "PUBLISH_GITEE")
            self.assertIn("CREATE_FRESH.json", result["next_command"])
            self.assertNotIn("require-host-ready", result["next_command"])

    def test_repeated_run_id_cannot_replace_the_request(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            a = base / "a"
            b = base / "b"
            for path in (a, b):
                path.mkdir()
                (path / "file").write_text("data")
            args = ["mpa.py", "start", "--goals", "REVIEW", "--work-root", str(base), "--run-id", "same", "--project-root"]
            self.assertEqual(run_script(*args, str(a)).returncode, 0)
            request = base / ".mindplus-agent/runs/same/request.json"
            before = request.read_bytes()
            result = run_script(*args, str(b))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, request.read_bytes())

    def test_current_review_overrides_external_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, external, _ = publish_fixture(base)
            result = run_script("mpa.py", "start", "--goals", "REVIEW,PUBLISH", "--project-root", str(project), "--work-root", str(base), "--run-id", "r", "--review-handoff", str(external), "--auth", "commit", "--auth", "push")
            self.assertEqual(result.returncode, 0, result.stdout)
            root = base / ".mindplus-agent/runs/r"
            current = host_ready_handoff(project)
            write_json(root / "handoffs/REVIEW_EXISTING.json", current)
            result = run_script("mpa.py", "transition", "--work-root", str(base), "--run-id", "r")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("REVIEW_EXISTING.json", json.loads(result.stdout)["next_command"])
            self.assertNotIn(str(external), json.loads(result.stdout)["next_command"])

    def test_direct_publication_can_record_result_without_review(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-project"
            project.mkdir()
            (project / "file").write_text("data")
            result = run_script("mpa.py", "start", "--goals", "PUBLISH", "--project-root", str(project), "--work-root", str(base), "--run-id", "p", "--auth", "commit", "--auth", "push")
            self.assertEqual(json.loads(result.stdout)["workflows"], ["PUBLISH_GITEE"])
            result = run_script("mpa.py", "handoff", "--work-root", str(base), "--run-id", "p", "--workflow", "PUBLISH_GITEE", "--status", "BLOCKED", "--outcome", "TOKEN_REQUIRED", "--reason-code", "AUTH.GITEE_TOKEN_MISSING")
            self.assertEqual(result.returncode, 0, result.stdout)
