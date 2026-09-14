import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_workflow import publish_fixture, host_ready_handoff, write_json, make_preflight, run_gitee, run_script, FAKE_TOKEN
import gitee_publish as pub


class PublicationRegressions(unittest.TestCase):
    def test_deleted_files_leave_commit_and_unchanged_commit_is_reused(self):
        for pre_staged in (False, True):
            with self.subTest(pre_staged=pre_staged), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                project, handoff, preflight = publish_fixture(base)
                def git(*args):
                    result = pub.git(project, *args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    return result.stdout.strip()
                git("init")
                git("config", "user.name", "Tester")
                git("config", "user.email", "t@example.com")
                (project / "old.txt").write_text("obsolete", encoding="utf-8")
                git("add", "extension", "old.txt")
                git("commit", "-m", "initial")
                (project / "old.txt").unlink()
                if pre_staged:
                    git("add", "-u", "--", "old.txt")
                write_json(handoff, host_ready_handoff(project, authorized=True))
                self.assertEqual(make_preflight(project, handoff, preflight).returncode, 0)
                common = ["--preflight", str(preflight), "--state-dir", str(base / "state")]
                for stage in (["plan"], ["commit", "--message", "delete obsolete"]):
                    result = run_gitee(stage + common, {"GITEE_TOKEN": FAKE_TOKEN})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("old.txt", git("ls-tree", "-r", "--name-only", "HEAD").splitlines())
                result = run_gitee(["commit", "--message", "reuse"] + common, {"GITEE_TOKEN": FAKE_TOKEN})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(json.loads(result.stdout)["reused_existing_commit"])

    def test_direct_publish_records_external_review_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, handoff, _ = publish_fixture(base)
            result = run_script("mpa.py", "start", "--goals", "PUBLISH", "--project-root", str(project),
                                "--work-root", str(base), "--review-handoff", str(handoff),
                                "--auth", "commit", "--auth", "push", "--run-id", "direct")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            args = ["mpa.py", "handoff", "--work-root", str(base), "--run-id", "direct", "--workflow", "PUBLISH_GITEE",
                    "--status", "PASS", "--outcome", "PUSHED"]
            for check in ("review_gate_current", "publication_set_reviewed", "git_commit", "gitee_repository", "remote_ref_verified"):
                args += ["--check", check + "=PASS", "--evidence", check + "=" + str(handoff)]
            result = run_script(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            recorded = json.loads((base / ".mindplus-agent/runs/direct/handoffs/PUBLISH_GITEE.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(recorded["input_provenance"]["path"]), handoff)

    def test_visibility_failure_preserves_verified_push_without_success_handoff(self):
        for response in ((403, {}), (200, {"private": True}), (200, {"private": False}), pub.StageBlocked({"reason_code": "NETWORK"})):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                context = {"project": base, "token": "fake", "state_dir": base, "project_sha256": "hash", "preflight_path": base / "preflight.json"}
                records = [{}, {"branch": "main", "commit_sha": "sha"}, {"remote_name": "origin", "owner_or_org": "owner", "repo_name": "repo", "clone_url": "https://gitee.com/owner/repo.git", "pending_visibility_promotion": True}]
                with patch.object(pub, "context", return_value=context), patch.object(pub, "load_stage", side_effect=records), patch.object(pub, "read_json", return_value={}), patch.object(pub, "drift_check"), patch.object(pub, "auth_environment", return_value={}), patch.object(pub, "git") as git, patch.object(pub, "compute_project_hash", return_value=("hash", 1)), patch.object(pub, "ensure_publication_topic", return_value={"status": "VERIFIED"}), patch.object(pub, "gitee_api", side_effect=[(200, {"commit": {"sha": "sha"}}), (200, {"commit": {"sha": "sha"}}), (200, {"full_name": "owner/repo", "name": "Display name", "private": True}), response, (200, {"full_name": "owner/repo", "private": response != (200, {"private": False})})]), contextlib.redirect_stdout(io.StringIO()) as output:
                    git.return_value.stdout = "sha"
                    code = pub.cmd_push(argparse.Namespace())
                result = json.loads(output.getvalue())
                success = response == (200, {"private": False})
                self.assertEqual(code, 0 if success else 2)
                self.assertEqual(result["status"], "PASS" if success else "BLOCKED")
                self.assertEqual(result["verified_remote_sha"], "sha")
                if not success:
                    self.assertIsNone(result["next_command"])
                    saved = json.loads((base / "publish-push.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["outcome"], "PUSHED_VISIBILITY_PENDING")

    def test_visibility_request_preserves_name_and_requires_get(self):
        private = {"full_name": "owner/repo", "name": "Existing Display Name", "private": True}
        for patch_response in ((400, {"messages": ["error"]}), (200, {"private": False}), pub.StageBlocked({"reason_code": "NETWORK"})):
            with self.subTest(patch_response=patch_response):
                with patch.object(pub, "gitee_api", side_effect=[(200, private), patch_response, (200, {**private, "private": False})]) as api:
                    result = pub.ensure_public_visibility("owner", "repo", "fake")
                self.assertEqual(result["status"], "PROMOTED_TO_PUBLIC")
                self.assertEqual(api.call_args_list[1].kwargs["body"], {"name": "Existing Display Name", "private": False})
                self.assertEqual(api.call_args_list[-1].args[:2], ("GET", "/repos/owner/repo"))
        with patch.object(pub, "gitee_api", side_effect=[(200, private), (200, {"private": False}), (200, private)]):
            self.assertEqual(pub.ensure_public_visibility("owner", "repo", "fake")["status"], "FAILED")

    def test_already_public_does_not_patch(self):
        with patch.object(pub, "gitee_api", return_value=(200, {"full_name": "owner/repo", "private": False})) as api:
            self.assertEqual(pub.ensure_public_visibility("owner", "repo", "fake")["status"], "PROMOTED_TO_PUBLIC")
            self.assertEqual(api.call_count, 1)

    def test_visibility_intent_survives_cleared_remote_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            write_json(state / "publish-remote.json", {"owner_or_org": "owner", "repo_name": "repo", "pending_visibility_promotion": False})
            write_json(state / "publish-push.json", {"clone_url": "https://gitee.com/owner/repo.git", "outcome": "PUSHED_VISIBILITY_PENDING"})
            self.assertTrue(pub.public_intent(state, "owner", "repo"))
            with self.assertRaises(pub.StageBlocked):
                pub.public_intent(state, "owner", "another")
            self.assertEqual(pub.decide_create_privacy(False, True), (False, True))
