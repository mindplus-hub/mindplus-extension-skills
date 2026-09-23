from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REFERENCES = ROOT / "references"
SWITCH_SCRIPTS = SCRIPTS / "switch"
SWITCH_REFERENCES = REFERENCES / "switch"
sys.path.insert(0, str(SCRIPTS))

from hash_project import compute_project_hash
from check_basic_review import BASIC_CHECKS


def run_script(name: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / name), *args],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_switch_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SWITCH_SCRIPTS / name), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request(
    goals: list[str],
    project_root: Path,
    *,
    auth: dict[str, bool] | None = None,
    **paths: str | None,
) -> dict:
    authorizations = {
        "local_write": True,
        "install": True,
        "build": True,
        "mindplus_ui": True,
        "commit": False,
        "create_repository": False,
        "push": False,
        "device_upload": False,
    }
    if auth:
        authorizations.update(auth)
    return {
        "goals": goals,
        "paths": {
            "v1_source": paths.get("v1_source"),
            "project_root": str(project_root),
            "extension_spec": paths.get("extension_spec"),
            "review_handoff": paths.get("review_handoff"),
        },
        "authorizations": authorizations,
    }


def basic_handoff(
    project_root: Path,
    *,
    authorized: bool = True,
    confirmed: bool = True,
) -> dict:
    from check_basic_review import BASIC_CHECKS
    report_path = basic_report_fixture(project_root)
    project_hash, _ = compute_project_hash(project_root)
    checks = [{"id": name, "layer": "STATIC", "claim": name, "required": True, "result": "PASS",
               "evidence": [str(report_path)], "confirmed_by": None} for name in sorted(BASIC_CHECKS)]
    if not confirmed:
        checks = [c for c in checks if c["id"] != "blocks_visible"]
    return {"schema_version": "mindplus-agent.handoff/v1", "run_id": "review-run", "parent_run_id": "parent-run",
            "workflow": "REVIEW_EXISTING", "producer": "mindplus-review", "state": "TERMINAL", "status": "PASS",
            "outcome": "REVIEWED_BASIC", "reason_code": None,
            "input_provenance": {"type": "EXISTING_V2", "path": str(project_root), "manifest": None, "sha256": project_hash, "commit": None},
            "project_root": str(project_root), "project_sha256": project_hash,
            "artifacts": [{"kind": "basic_review", "path": str(report_path), "sha256": None}], "checks": checks,
            "authorizations": {"local_write": False, "install": False, "build": True, "mindplus_ui": True,
                               "commit": authorized, "create_repository": False, "push": authorized, "device_upload": False},
            "next": [{"workflow": "PUBLISH_GITEE", "condition": "BASIC and current hashes"}]}


def basic_report_fixture(project):
    # Synthetic evidence for contract tests only; never treated as a real extension review.
    import zipfile
    from hash_project import file_digest
    from check_basic_review import EVIDENCE_CHECKS
    root = project / ".mindplus-agent" / "fixture-basic"
    root.mkdir(parents=True, exist_ok=True)
    package = root / "extension.zip"
    with zipfile.ZipFile(package, "w") as z:
        z.writestr("main.js", "test artifact")
        z.writestr("config.json", "{}")
    log = root / "observations.log"
    log.write_text("Synthetic test evidence: build and block observation fixture", encoding="utf-8")
    digest = file_digest(package)
    checks = {name: {"result": "PASS", "method": "unit-test fixture", "summary": "synthetic verification",
                    "artifact_sha256": digest, "evidence": [{"path": str(log), "sha256": file_digest(log)}]}
              for name in EVIDENCE_CHECKS}
    checks["builder_build"]["exit_code"] = 0
    report = {"schema_version": "mindplus.review-basic/v1", "status": "PASS", "project_root": str(project),
              "project_sha256": compute_project_hash(project)[0], "artifact": {"path": str(package), "sha256": digest}, "checks": checks}
    path = root / "basic-review.json"
    write_json(path, report)
    return path


def lite_fixture(project):
    path = project.parent / (project.name + "-lite-selection.json")
    write_json(path, {"schema_version": "mindplus.review-lite-selection/v1", "status": "PASS",
                     "project_root": str(project), "decision": "EXPLICIT_SOURCE_UNVERIFIED", "comparison": "fixture only",
                     "source_decision": "explicit local source in fixture", "limitation": "offline test"})
    return path


class RouteTests(unittest.TestCase):
    def test_convert_publish_skips_independent_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            v1 = base / "v1"
            v1.mkdir()
            input_path = base / "request.json"
            write_json(
                input_path,
                request(
                    ["CONVERT", "PUBLISH"],
                    base / "ext2-ul-v2",
                    auth={"commit": True, "push": True},
                    v1_source=str(v1),
                ),
            )
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            routed = json.loads(completed.stdout)
            self.assertEqual(
                routed["workflows"],
                ["CONVERT_FRESH", "REVIEW_EXISTING", "PUBLISH_GITEE"],
            )

    def test_sync_is_explicitly_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "existing"
            project.mkdir()
            (project / "config.json").write_text("{}", encoding="utf-8")
            input_path = base / "request.json"
            write_json(input_path, request(["SYNC"], project))
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 3)
            routed = json.loads(completed.stdout)
            self.assertEqual(routed["reason_code"], "ROUTE.UNSUPPORTED_EXISTING_V2_SYNC")
            self.assertEqual(routed["workflows"], [])

    def test_convert_never_overwrites_nonempty_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            v1 = base / "v1"
            project = base / "ext2-ul-v2"
            v1.mkdir()
            project.mkdir()
            (project / "owned.txt").write_text("user", encoding="utf-8")
            input_path = base / "request.json"
            write_json(input_path, request(["CONVERT"], project, v1_source=str(v1)))
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 3)
            routed = json.loads(completed.stdout)
            self.assertEqual(routed["reason_code"], "ROUTE.UNSUPPORTED_EXISTING_V2_SYNC")
            self.assertEqual((project / "owned.txt").read_text(encoding="utf-8"), "user")

    def test_direct_publish_with_handoff_routes_only_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            handoff = base / "handoff.json"
            write_json(handoff, basic_handoff(project))
            input_path = base / "request.json"
            write_json(
                input_path,
                request(
                    ["PUBLISH"],
                    project,
                    auth={"commit": True, "push": True},
                    review_handoff=str(handoff),
                ),
            )
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(json.loads(completed.stdout)["workflows"], ["REVIEW_EXISTING", "PUBLISH_GITEE"])

    def test_publish_without_push_authorization_waits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            handoff = base / "handoff.json"
            write_json(handoff, basic_handoff(project))
            input_path = base / "request.json"
            write_json(input_path, request(["PUBLISH"], project, review_handoff=str(handoff)))
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 3)
            routed = json.loads(completed.stdout)
            self.assertEqual(routed["reason_code"], "AUTH.PUSH_NOT_AUTHORIZED")
            self.assertEqual(routed["state"], "WAITING_USER")
            self.assertEqual(routed["workflows"], [])

    def test_convert_requires_local_write_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            v1 = base / "v1"
            v1.mkdir()
            input_path = base / "request.json"
            write_json(
                input_path,
                request(["CONVERT"], base / "ext2-ul-v2", auth={"local_write": False}, v1_source=str(v1)),
            )
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 3)
            routed = json.loads(completed.stdout)
            self.assertEqual(routed["reason_code"], "AUTH.LOCAL_WRITE_REQUIRED")
            self.assertEqual(routed["state"], "WAITING_USER")

    def test_external_switch_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            v1 = base / "v1"
            v1.mkdir()
            value = request(["CONVERT"], base / "ext2-ul-v2", v1_source=str(v1))
            value["paths"]["mindplus_switch_root"] = str(base / "external-switch")
            input_path = base / "request.json"
            write_json(input_path, value)
            completed = run_script("route_workflow.py", "--input", str(input_path))
            self.assertEqual(completed.returncode, 2)
            routed = json.loads(completed.stdout)
            self.assertEqual(routed["reason_code"], "INPUT.INVALID_ROUTE_REQUEST")
            self.assertIn("mindplus_switch_root", routed["message"])
            self.assertEqual(routed["workflows"], [])


class TokenTests(unittest.TestCase):
    @staticmethod
    def _env_without_token(**overrides: str) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("GITEE_TOKEN", None)
        env.pop("GITEE_ACCESS_TOKEN", None)
        env["GITEE_TOKEN_FILE"] = str(Path(tempfile.gettempdir()) / "no-such-gitee-token-file")
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = str(Path(tempfile.gettempdir()) / "no-such-gitconfig")
        env.update(overrides)
        return env

    def test_missing_token_waits_without_secret(self) -> None:
        completed = run_script("check_gitee_token.py", env=self._env_without_token())
        self.assertEqual(completed.returncode, 3)
        output = json.loads(completed.stdout)
        self.assertEqual(output["state"], "WAITING_USER")
        self.assertEqual(output["reason_code"], "AUTH.GITEE_TOKEN_MISSING")
        self.assertFalse(output["token_present"])

    @unittest.skipIf(os.name == "nt", "Windows local tokens use Windows Credential Manager")
    def test_token_file_source_is_accepted_without_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "gitee-token"
            secret = "file-sourced-test-token"
            token_file.write_text(secret + "\n", encoding="utf-8")
            completed = run_script(
                "check_gitee_token.py",
                env=self._env_without_token(GITEE_TOKEN_FILE=str(token_file)),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertTrue(output["token_present"])
            self.assertTrue(output["source"].startswith("file:"))
            self.assertNotIn(secret, completed.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows Credential Manager test")
    def test_windows_credential_manager_source_is_accepted_without_secret_output(self) -> None:
        import check_gitee_token as token_checker

        source = "windows-credential-manager:git:https://gitee.com"
        secret = "credential-manager-test-token"
        completed = subprocess.CompletedProcess(
            ["git", "credential", "fill"],
            0,
            stdout=f"protocol=https\nhost=gitee.com\nusername=mds890mn\npassword={secret}\n",
            stderr="",
        )
        with patch.object(token_checker.subprocess, "run", return_value=completed) as run:
            resolved_source, resolved_token = token_checker.resolve_windows_credential()
        self.assertEqual(resolved_source, source)
        self.assertEqual(resolved_token, secret)
        self.assertEqual(run.call_args.args[0], ["git", "credential", "fill"])
        self.assertEqual(run.call_args.kwargs["input"], "protocol=https\nhost=gitee.com\n\n")

    @unittest.skipUnless(os.name == "nt", "Windows Credential Manager test")
    def test_resolve_token_uses_windows_credential_manager(self) -> None:
        import check_gitee_token as token_checker

        source = "windows-credential-manager:git:https://gitee.com"
        with patch.dict(os.environ, {}, clear=True), patch.object(
            token_checker, "resolve_windows_credential", return_value=(source, "credential-manager-test-token")
        ):
            resolved_source, resolved_token = token_checker.resolve_token()
        self.assertEqual(resolved_source, source)
        self.assertEqual(resolved_token, "credential-manager-test-token")

    def test_present_token_is_never_printed(self) -> None:
        secret = "test-token-value-that-must-not-appear"
        env = dict(os.environ)
        env["GITEE_TOKEN"] = secret
        env.pop("GITEE_ACCESS_TOKEN", None)
        completed = run_script("check_gitee_token.py", env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertNotIn(secret, completed.stdout)
        output = json.loads(completed.stdout)
        self.assertTrue(output["token_present"])
        self.assertEqual(output["source"], "env:GITEE_TOKEN")

    def test_publish_preflight_checks_token_before_paths_or_git(self) -> None:
        completed = run_script(
            "prepare_gitee_publish.py",
            "--project-root",
            str(ROOT / "does-not-exist"),
            "--review-handoff",
            str(ROOT / "also-does-not-exist.json"),
            env=self._env_without_token(),
        )
        self.assertEqual(completed.returncode, 3, completed.stderr or completed.stdout)
        output = json.loads(completed.stdout)
        self.assertEqual(output["reason_code"], "AUTH.GITEE_TOKEN_MISSING")
        self.assertIn("No project, Git, or Gitee operation was performed", output["message"])

    def test_publish_preflight_allows_uninitialized_project_after_basic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-project"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            handoff = base / "handoff.json"
            write_json(handoff, basic_handoff(project))
            env = dict(os.environ)
            env["GITEE_TOKEN"] = "test-token-not-for-network"
            env.pop("GITEE_ACCESS_TOKEN", None)
            completed = run_script(
                "prepare_gitee_publish.py",
                "--project-root",
                str(project),
                "--review-handoff",
                str(handoff),
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["outcome"], "PUBLISH_PREPARE_READY")
            self.assertEqual(output["git"]["state"], "NOT_INITIALIZED")

    def test_publish_preflight_rejects_stale_basic_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-project"
            project.mkdir()
            source = project / "extension.js"
            source.write_text("before", encoding="utf-8")
            handoff = base / "handoff.json"
            write_json(handoff, basic_handoff(project))
            source.write_text("after", encoding="utf-8")
            env = dict(os.environ)
            env["GITEE_TOKEN"] = "test-token-not-for-network"
            env.pop("GITEE_ACCESS_TOKEN", None)
            completed = run_script(
                "prepare_gitee_publish.py",
                "--project-root",
                str(project),
                "--review-handoff",
                str(handoff),
                env=env,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["reason_code"], "REVIEW.HANDOFF_INVALID")

    def test_publish_preflight_rejects_unauthorized_push(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-project"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            handoff = base / "handoff.json"
            write_json(handoff, basic_handoff(project, authorized=False))
            env = dict(os.environ)
            env["GITEE_TOKEN"] = "test-token-not-for-network"
            env.pop("GITEE_ACCESS_TOKEN", None)
            completed = run_script(
                "prepare_gitee_publish.py",
                "--project-root",
                str(project),
                "--review-handoff",
                str(handoff),
                env=env,
            )
            self.assertEqual(completed.returncode, 3)
            output = json.loads(completed.stdout)
            self.assertEqual(output["reason_code"], "AUTH.PUSH_NOT_AUTHORIZED")
            self.assertEqual(output["state"], "WAITING_USER")

    def test_publish_preflight_create_repo_flag_requires_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-project"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            handoff = base / "handoff.json"
            write_json(handoff, basic_handoff(project))
            env = dict(os.environ)
            env["GITEE_TOKEN"] = "test-token-not-for-network"
            env.pop("GITEE_ACCESS_TOKEN", None)
            completed = run_script(
                "prepare_gitee_publish.py",
                "--project-root",
                str(project),
                "--review-handoff",
                str(handoff),
                "--create-repo",
                env=env,
            )
            self.assertEqual(completed.returncode, 3)
            output = json.loads(completed.stdout)
            self.assertEqual(output["reason_code"], "AUTH.CREATE_REPOSITORY_NOT_AUTHORIZED")


class HandoffTests(unittest.TestCase):
    def test_valid_basic_handoff_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            handoff = project / ".mindplus-agent" / "handoff.json"
            write_json(handoff, basic_handoff(project))
            completed = run_script(
                "validate_handoff.py",
                "--input",
                str(handoff),
                "--require-outcome",
                "REVIEWED_BASIC",
                "--check-artifacts",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_basic_missing_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = basic_handoff(project)
            value["checks"] = value["checks"][:-1]
            handoff = project / ".mindplus-agent" / "handoff.json"
            write_json(handoff, value)
            completed = run_script("validate_handoff.py", "--input", str(handoff))
            self.assertEqual(completed.returncode, 1)
            self.assertIn("BASIC review requires evidenced PASS", completed.stdout)

    def test_basic_without_observation_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            handoff = project / ".mindplus-agent" / "handoff.json"
            write_json(handoff, basic_handoff(project, confirmed=False))
            completed = run_script("validate_handoff.py", "--input", str(handoff))
            self.assertEqual(completed.returncode, 1)
            self.assertIn("BASIC review requires evidenced PASS: blocks_visible", completed.stdout)

    def test_passing_required_check_without_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = basic_handoff(project)
            value["checks"][0]["evidence"] = []
            handoff = project / ".mindplus-agent" / "handoff.json"
            write_json(handoff, value)
            completed = run_script("validate_handoff.py", "--input", str(handoff))
            self.assertEqual(completed.returncode, 1)
            self.assertIn("passing required check has no evidence", completed.stdout)


class HashTests(unittest.TestCase):
    def test_junction_inside_project_is_rejected(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows junctions only")
        try:
            import _winapi
        except ImportError:
            self.skipTest("_winapi unavailable")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"
            real.mkdir()
            (real / "config.json").write_text("{}", encoding="utf-8")
            junction = base / "junction"
            try:
                _winapi.CreateJunction(str(real), str(junction))
            except OSError as exc:
                self.skipTest(f"cannot create junction: {exc}")
            completed = run_script("hash_project.py", "--project-root", str(base))
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["status"], "BLOCKED")
            self.assertIn("junction", output["error"])


class RunAndContractTests(unittest.TestCase):
    def test_parent_run_initializes_after_passing_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-project"
            spec = base / "spec.json"
            spec.write_text("{}", encoding="utf-8")
            request_path = base / "request.json"
            route_path = base / "route.json"
            write_json(request_path, request(["CREATE"], project, extension_spec=str(spec)))
            routed = run_script("route_workflow.py", "--input", str(request_path), "--output", str(route_path))
            self.assertEqual(routed.returncode, 0, routed.stderr or routed.stdout)
            initialized = run_script(
                "init_run.py",
                "--work-root",
                str(base),
                "--request",
                str(request_path),
                "--route-result",
                str(route_path),
                "--run-id",
                "test-run",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr or initialized.stdout)
            run_root = Path(json.loads(initialized.stdout)["run_root"])
            self.assertTrue((run_root / "run.json").is_file())
            self.assertTrue((run_root / "handoffs").is_dir())
            self.assertTrue((run_root / "evidence").is_dir())

    def test_parent_run_rejects_token_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-project"
            request_value = request(["CREATE"], project)
            request_value["GITEE_TOKEN"] = "must-not-be-recorded"
            request_path = base / "request.json"
            route_path = base / "route.json"
            write_json(request_path, request_value)
            write_json(
                route_path,
                {
                    "schema_version": "mindplus-agent.route-result/v1",
                    "state": "RUNNING",
                    "status": "PASS",
                    "reason_code": None,
                    "message": "test",
                    "facts": {},
                    "workflows": ["CREATE_FRESH"],
                    "leaf_references": ["references/workflows/create.md"],
                },
            )
            initialized = run_script(
                "init_run.py",
                "--work-root",
                str(base),
                "--request",
                str(request_path),
                "--route-result",
                str(route_path),
                "--run-id",
                "secret-test",
            )
            self.assertEqual(initialized.returncode, 2)
            self.assertFalse((base / ".mindplus-agent" / "runs" / "secret-test").exists())
            self.assertNotIn("must-not-be-recorded", initialized.stdout)

    def test_all_json_resources_parse(self) -> None:
        for path in REFERENCES.rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8-sig"))

    def test_registry_contains_only_five_supported_leaves(self) -> None:
        registry = json.loads((REFERENCES / "workflow-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(registry["workflows"]),
            {"CONVERT_FRESH", "CREATE_FRESH", "UPGRADE_EXISTING", "REVIEW_EXISTING", "PUBLISH_GITEE"},
        )

    def test_entrypoint_references_exist(self) -> None:
        for relative in (
            "routing.md",
            "handoff.md",
            "evidence.md",
            "workflows/switch.md",
            "workflows/create.md",
            "workflows/review.md",
            "workflows/gitee-publish.md",
            "switch/conventions.md",
            "switch/block-organization.md",
            "switch/official-corpus.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((REFERENCES / relative).is_file())


class EmbeddedSwitchTests(unittest.TestCase):
    def test_embedded_reference_bundle_validates_offline(self) -> None:
        completed = run_switch_script(
            "check_reference_release.py",
            "--skill-root",
            str(ROOT),
            "--offline",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "BUNDLED_ONLY")
        self.assertEqual(
            Path(result["active_root"]),
            (SWITCH_REFERENCES / "generated").resolve(),
        )

    def test_all_embedded_switch_scripts_expose_cli(self) -> None:
        scripts = sorted(SWITCH_SCRIPTS.glob("*.py"))
        self.assertEqual(len(scripts), 14)
        for script in scripts:
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_route_contract_has_no_external_switch_path(self) -> None:
        schema = json.loads(
            (REFERENCES / "contracts" / "route-request.schema.json").read_text(encoding="utf-8")
        )
        path_properties = schema["properties"]["paths"]["properties"]
        self.assertNotIn("mindplus_switch_root", path_properties)
        leaf = (REFERENCES / "workflows" / "switch.md").read_text(encoding="utf-8")
        self.assertIn("scripts/switch/init_run.py", leaf)
        self.assertIn("references/switch/", leaf)

    def test_isolated_package_copy_needs_no_sibling_switch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            package = base / "installed" / "mindplus-extension-skills"
            package.parent.mkdir()
            shutil.copytree(
                ROOT,
                package,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            self.assertFalse((package.parent / "mindplus-switch").exists())

            reference_check = subprocess.run(
                [
                    sys.executable,
                    str(package / "scripts" / "switch" / "check_reference_release.py"),
                    "--offline",
                ],
                cwd=package,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                reference_check.returncode,
                0,
                reference_check.stderr or reference_check.stdout,
            )

            v1 = base / "v1"
            v1.mkdir()
            write_json(
                v1 / "config.json",
                {
                    "version": "1.0.0",
                    "name": {"zh-cn": "示例", "en": "Example"},
                    "description": {"zh-cn": "", "en": ""},
                    "author": "tester",
                },
            )
            inventory = base / "inventory.json"
            write_json(
                inventory,
                {
                    "identity": {
                        "canonical_v2_id": "example",
                        "expected_compatibility_id": "tester/example",
                    }
                },
            )
            generated_config = base / "generated" / "config.json"
            skeleton = subprocess.run(
                [
                    sys.executable,
                    str(package / "scripts" / "switch" / "create_config_skeleton.py"),
                    "--source",
                    str(v1),
                    "--inventory",
                    str(inventory),
                    "--mode",
                    "UPLOAD",
                    "--output",
                    str(generated_config),
                ],
                cwd=package,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(skeleton.returncode, 0, skeleton.stderr or skeleton.stdout)
            self.assertEqual(
                json.loads(generated_config.read_text(encoding="utf-8"))["id"],
                "example",
            )

            request_path = base / "request.json"
            write_json(request_path, request(["CONVERT"], base / "ext2-ul-v2", v1_source=str(v1)))
            routed = subprocess.run(
                [
                    sys.executable,
                    str(package / "scripts" / "route_workflow.py"),
                    "--input",
                    str(request_path),
                ],
                cwd=package,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(routed.returncode, 0, routed.stderr or routed.stdout)
            self.assertEqual(json.loads(routed.stdout)["workflows"], ["CONVERT_FRESH", "REVIEW_EXISTING"])


class MpaTests(unittest.TestCase):
    def run_mpa(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_script("mpa.py", *args)

    def test_mpa_cli_help_exposes_subcommands(self) -> None:
        completed = self.run_mpa("--help")
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        for command in ("start", "handoff", "transition", "resume"):
            self.assertIn(command, completed.stdout)

    def test_mpa_start_creates_run_and_points_at_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = base / "spec.json"
            spec.write_text("{}", encoding="utf-8")
            completed = self.run_mpa(
                "start",
                "--goals", "CREATE",
                "--project-root", str(base / "ext2-ul-project"),
                "--extension-spec", str(spec),
                "--work-root", str(base),
                "--run-id", "t1",
                "--auth", "local_write",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["status"], "PASS")
            self.assertEqual(output["current_workflow"], "CREATE_FRESH")
            run_file = Path(output["run_root"]) / "run.json"
            self.assertTrue(run_file.is_file())
            self.assertIn("create.md", output["next_command"])
            self.assertIn("check_reference_release.py", output["next_command"])

    def test_mpa_start_blocked_without_push_auth_lists_fix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            completed = self.run_mpa(
                "start",
                "--goals", "REVIEW,PUBLISH",
                "--project-root", str(project),
                "--work-root", str(base),
                "--run-id", "t2",
            )
            self.assertEqual(completed.returncode, 3)
            output = json.loads(completed.stdout)
            self.assertEqual(output["reason_code"], "AUTH.PUSH_NOT_AUTHORIZED")
            self.assertIn("--auth commit --auth push", output["next_command"])

    def test_mpa_start_input_errors_name_actionable_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cases = (
                (
                    ("start", "--goals", "REVIEW", "--project-root", str(base / "project"),
                     "--work-root", str(base / "missing")),
                    "WORKSPACE.WORK_ROOT_MISSING",
                    "Create the work-root directory",
                ),
                (
                    ("start", "--goals", "REVIEW", "--project-root", str(base / "project"),
                     "--work-root", str(base), "--auth", "unsupported"),
                    "INPUT.UNKNOWN_AUTHORIZATION",
                    "valid_values",
                ),
                (
                    ("start", "--goals", "REVIEW", "--project-root", str(base / "project"),
                     "--work-root", str(base), "--run-id", "bad/run"),
                    "WORKSPACE.RUN_INIT",
                    "hex run-id",
                ),
            )
            for arguments, reason_code, recovery in cases:
                with self.subTest(reason_code=reason_code):
                    completed = self.run_mpa(*arguments)
                    self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                    output = json.loads(completed.stdout)
                    self.assertEqual(output["reason_code"], reason_code)
                    self.assertIn(recovery, output["next_command"])

    def test_mpa_start_request_mismatch_names_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = base / "spec.json"
            spec.write_text("{}", encoding="utf-8")
            arguments = (
                "start", "--goals", "CREATE", "--project-root", str(base / "ext2-ul-project"),
                "--extension-spec", str(spec), "--work-root", str(base), "--run-id", "mismatch",
                "--auth", "local_write",
            )
            self.assertEqual(self.run_mpa(*arguments).returncode, 0)
            completed = self.run_mpa(*arguments, "--auth", "build")
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["reason_code"], "WORKSPACE.RUN_REQUEST_MISMATCH")
            self.assertIn("mpa.py resume", output["next_command"])

    def test_mpa_invalid_route_request_names_recovery(self) -> None:
        import mpa

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output_stream = io.StringIO()
            arguments = argparse.Namespace(
                work_root=base,
                goals="REVIEW",
                project_root=base / "project",
                v1_source=None,
                extension_spec=None,
                review_handoff=None,
                run_id=None,
                auth=None,
                review_profile="BASIC",
                keep_evidence=False,
            )
            with patch.object(mpa, "read_route_json", side_effect=ValueError("bad registry")), redirect_stdout(output_stream):
                self.assertEqual(mpa.cmd_start(arguments), 2)
            output = json.loads(output_stream.getvalue())
            self.assertEqual(output["reason_code"], "INPUT.INVALID_ROUTE_REQUEST")
            self.assertIn("fix the reported field", output["next_command"])

    def test_mpa_start_is_idempotent_for_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = base / "spec.json"
            spec.write_text("{}", encoding="utf-8")
            arguments = (
                "start",
                "--goals", "CREATE",
                "--project-root", str(base / "ext2-ul-project"),
                "--extension-spec", str(spec),
                "--work-root", str(base),
                "--run-id", "t3",
                "--auth", "local_write",
            )
            first = self.run_mpa(*arguments)
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            second = self.run_mpa(*arguments)
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            self.assertEqual(json.loads(second.stdout)["status"], "PASS_IDEMPOTENT")

    def test_mpa_reported_findings_completes_review_only_run_and_retains_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "project"
            project.mkdir()
            (project / "config.json").write_text("{}", encoding="utf-8")
            evidence = base / "static-review.log"
            evidence.write_text("reviewed", encoding="utf-8")
            started = self.run_mpa(
                "start", "--goals", "REVIEW", "--project-root", str(project),
                "--work-root", str(base), "--run-id", "report-only",
            )
            self.assertEqual(started.returncode, 0, started.stderr or started.stdout)

            handoff_arguments = [
                "handoff", "--work-root", str(base), "--run-id", "report-only",
                "--workflow", "REVIEW_EXISTING", "--status", "PASS", "--outcome", "REPORTED_FINDINGS",
            ]
            for check_id in ("config_schema", "extension_static_integrity", "source_semantics", "malicious_code_review"):
                handoff_arguments += ["--check", check_id + "=PASS", "--evidence", check_id + "=" + str(evidence)]
            for check_id in ("builder_build", "blocks_visible", "blocks_functional", "package_size"):
                handoff_arguments += ["--check", check_id + "=NOT_RUN", "--optional", check_id]
            recorded = self.run_mpa(*handoff_arguments)
            self.assertEqual(recorded.returncode, 0, recorded.stderr or recorded.stdout)
            self.assertEqual(json.loads(recorded.stdout)["state"], "TERMINAL")

            completed = self.run_mpa("transition", "--work-root", str(base), "--run-id", "report-only")
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["message"], "report-first run complete; evidence retained")
            self.assertFalse(output["evidence_cleaned"])
            self.assertTrue(Path(output["run_root"]).is_dir())

    def test_mpa_reported_findings_cannot_replace_basic_before_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "project"
            project.mkdir()
            (project / "config.json").write_text("{}", encoding="utf-8")
            evidence = base / "static-review.log"
            evidence.write_text("reviewed", encoding="utf-8")
            started = self.run_mpa(
                "start", "--goals", "REVIEW,PUBLISH", "--project-root", str(project),
                "--work-root", str(base), "--run-id", "report-before-publish",
                "--auth", "commit", "--auth", "push",
            )
            self.assertEqual(started.returncode, 0, started.stderr or started.stdout)

            handoff_arguments = [
                "handoff", "--work-root", str(base), "--run-id", "report-before-publish",
                "--workflow", "REVIEW_EXISTING", "--status", "PASS", "--outcome", "REPORTED_FINDINGS",
            ]
            for check_id in ("config_schema", "extension_static_integrity", "source_semantics", "malicious_code_review"):
                handoff_arguments += ["--check", check_id + "=PASS", "--evidence", check_id + "=" + str(evidence)]
            for check_id in ("builder_build", "blocks_visible", "blocks_functional", "package_size"):
                handoff_arguments += ["--check", check_id + "=NOT_RUN", "--optional", check_id]
            rejected = self.run_mpa(*handoff_arguments)
            self.assertEqual(rejected.returncode, 1, rejected.stderr or rejected.stdout)
            self.assertIn("REPORTED_FINDINGS is only valid for a review-only run", json.loads(rejected.stdout)["errors"])

    def _convert_run(self, base: Path) -> Path:
        v1 = base / "v1"
        v1.mkdir()
        (v1 / "config.json").write_text("{}", encoding="utf-8")
        evidence = base / "record" / "conversion-check.json"
        evidence.parent.mkdir()
        evidence.write_text("{}", encoding="utf-8")
        started = self.run_mpa(
            "start",
            "--goals", "CONVERT,REVIEW,PUBLISH",
            "--project-root", str(base / "ext2-ul-v2"),
            "--v1-source", str(v1),
            "--work-root", str(base),
            "--run-id", "conv",
            "--auth", "local_write", "--auth", "commit", "--auth", "push",
        )
        self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
        return evidence

    def test_mpa_handoff_writes_valid_converted_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence = self._convert_run(base)
            project = base / "ext2-ul-v2"
            (project / "extension").mkdir(parents=True)
            (project / "extension" / "config.json").write_text("{}", encoding="utf-8")
            completed = self.run_mpa(
                "handoff",
                "--work-root", str(base),
                "--run-id", "conv",
                "--workflow", "CONVERT_FRESH",
                "--status", "PASS",
                "--outcome", "CONVERTED",
                "--check", "conversion_check=PASS",
                "--evidence", f"conversion_check={evidence}",
                "--check", "lite_source_selection=PASS", "--evidence", "lite_source_selection=" + str(lite_fixture(project)),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            handoff_path = Path(json.loads(completed.stdout)["handoff_path"])
            self.assertTrue(handoff_path.is_file())
            validated = run_script(
                "validate_handoff.py",
                "--input", str(handoff_path),
                "--require-outcome", "CONVERTED",
            )
            self.assertEqual(validated.returncode, 0, validated.stderr or validated.stdout)

    def test_mpa_handoff_refuses_gui_pass_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            evidence = base / "ev.json"
            evidence.write_text("{}", encoding="utf-8")
            started = self.run_mpa(
                "start",
                "--goals", "REVIEW,PUBLISH",
                "--project-root", str(project),
                "--work-root", str(base),
                "--run-id", "rev",
                "--auth", "commit", "--auth", "push",
            )
            self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
            completed = self.run_mpa(
                "handoff",
                "--work-root", str(base),
                "--run-id", "rev",
                "--workflow", "REVIEW_EXISTING",
                "--status", "PASS",
                "--outcome", "REVIEWED_BASIC",
                "--check", "mindplus_import=PASS",
                "--evidence", f"mindplus_import={evidence}",
            )
            self.assertEqual(completed.returncode, 1)
            output = json.loads(completed.stdout)
            self.assertEqual(output["reason_code"], "INPUT.INVALID_HANDOFF")
            self.assertTrue(output["errors"])
            handoffs = base / ".mindplus-agent" / "runs" / "rev" / "handoffs"
            self.assertFalse((handoffs / "REVIEW_EXISTING.json").exists())

    def test_mpa_handoff_refuses_pass_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence = self._convert_run(base)
            project = base / "ext2-ul-v2"
            (project / "extension").mkdir(parents=True)
            (project / "extension" / "config.json").write_text("{}", encoding="utf-8")
            completed = self.run_mpa(
                "handoff",
                "--work-root", str(base),
                "--run-id", "conv",
                "--workflow", "CONVERT_FRESH",
                "--status", "PASS",
                "--outcome", "CONVERTED",
                "--check", "conversion_check=PASS",
            )
            self.assertEqual(completed.returncode, 1)
            output = json.loads(completed.stdout)
            self.assertTrue(any("evidence" in error for error in output["errors"]))
            self.assertFalse((base / ".mindplus-agent" / "runs" / "conv" / "handoffs" / "CONVERT_FRESH.json").exists())

    def test_mpa_transition_advances_to_publish_after_basic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            evidence = base / "ev.json"
            evidence.write_text("{}", encoding="utf-8")
            self.run_mpa(
                "start",
                "--goals", "REVIEW,PUBLISH",
                "--project-root", str(project),
                "--work-root", str(base),
                "--run-id", "adv",
                "--auth", "commit", "--auth", "push",
            )
            handoff_arguments: list[str] = [
                "handoff",
                "--work-root", str(base),
                "--run-id", "adv",
                "--workflow", "REVIEW_EXISTING",
                "--status", "PASS",
                "--outcome", "REVIEWED_BASIC",
                "--check", "builder_build=PASS",
                "--evidence", f"builder_build={evidence}",
            ]
            for check_id in sorted(BASIC_CHECKS - {"builder_build"}):
                handoff_arguments += [
                    "--check", f"{check_id}=PASS",
                    "--evidence", f"{check_id}={evidence}",
                    "--confirmed", check_id,
                ]
            written = self.run_mpa(*handoff_arguments, "--artifact", "basic_review=" + str(basic_report_fixture(project)))
            self.assertEqual(written.returncode, 0, written.stderr or written.stdout)
            completed = self.run_mpa("transition", "--work-root", str(base), "--run-id", "adv")
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["advanced_to"], "PUBLISH_GITEE")
            self.assertIn("prepare_gitee_publish.py", output["next_command"])
            self.assertIn("REVIEW_EXISTING.json", output["next_command"])
            run_record = json.loads((base / ".mindplus-agent" / "runs" / "adv" / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_record["current_workflow"], "PUBLISH_GITEE")

    def test_mpa_transition_rejects_stale_review_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            evidence = base / "ev.json"
            evidence.write_text("{}", encoding="utf-8")
            self.run_mpa(
                "start",
                "--goals", "REVIEW,PUBLISH",
                "--project-root", str(project),
                "--work-root", str(base),
                "--run-id", "stale",
                "--auth", "commit", "--auth", "push",
            )
            handoff_arguments: list[str] = [
                "handoff",
                "--work-root", str(base),
                "--run-id", "stale",
                "--workflow", "REVIEW_EXISTING",
                "--status", "PASS",
                "--outcome", "REVIEWED_BASIC",
                "--check", "builder_build=PASS",
                "--evidence", f"builder_build={evidence}",
            ]
            for check_id in sorted(BASIC_CHECKS - {"builder_build"}):
                handoff_arguments += [
                    "--check", f"{check_id}=PASS",
                    "--evidence", f"{check_id}={evidence}",
                    "--confirmed", check_id,
                ]
            self.run_mpa(*handoff_arguments, "--artifact", "basic_review=" + str(basic_report_fixture(project)))
            (project / "package.json").write_text('{"changed": true}', encoding="utf-8")
            completed = self.run_mpa("transition", "--work-root", str(base), "--run-id", "stale")
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(json.loads(completed.stdout)["reason_code"], "TRANSITION.INVALID_HANDOFF")

    def test_mpa_resume_lists_runs_and_reports_position(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = base / "spec.json"
            spec.write_text("{}", encoding="utf-8")
            self.run_mpa(
                "start",
                "--goals", "CREATE",
                "--project-root", str(base / "ext2-ul-project"),
                "--extension-spec", str(spec),
                "--work-root", str(base),
                "--run-id", "r1",
                "--auth", "local_write",
            )
            listed = self.run_mpa("resume", "--work-root", str(base))
            self.assertEqual(listed.returncode, 0, listed.stderr or listed.stdout)
            run_ids = [entry["run_id"] for entry in json.loads(listed.stdout)["runs"]]
            self.assertIn("r1", run_ids)
            position = self.run_mpa("resume", "--work-root", str(base), "--run-id", "r1")
            self.assertEqual(position.returncode, 0, position.stderr or position.stdout)
            output = json.loads(position.stdout)
            self.assertEqual(output["current_workflow"], "CREATE_FRESH")
            self.assertIn("create.md", output["next_command"])

    def test_mpa_golden_chain_reaches_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence = self._convert_run(base)
            project = base / "ext2-ul-v2"
            (project / "extension").mkdir(parents=True)
            (project / "extension" / "config.json").write_text("{}", encoding="utf-8")

            converted = self.run_mpa(
                "handoff",
                "--work-root", str(base),
                "--run-id", "conv",
                "--workflow", "CONVERT_FRESH",
                "--status", "PASS",
                "--outcome", "CONVERTED",
                "--check", "conversion_check=PASS",
                "--evidence", f"conversion_check={evidence}",
                "--check", "lite_source_selection=PASS", "--evidence", "lite_source_selection=" + str(lite_fixture(project)),
            )
            self.assertEqual(converted.returncode, 0, converted.stderr or converted.stdout)

            to_review = self.run_mpa("transition", "--work-root", str(base), "--run-id", "conv")
            self.assertEqual(to_review.returncode, 0, to_review.stderr or to_review.stdout)
            self.assertEqual(json.loads(to_review.stdout)["advanced_to"], "REVIEW_EXISTING")

            review_arguments: list[str] = [
                "handoff",
                "--work-root", str(base),
                "--run-id", "conv",
                "--workflow", "REVIEW_EXISTING",
                "--status", "PASS",
                "--outcome", "REVIEWED_BASIC",
                "--check", "builder_build=PASS",
                "--evidence", f"builder_build={evidence}",
            ]
            for check_id in sorted(BASIC_CHECKS - {"builder_build"}):
                review_arguments += [
                    "--check", f"{check_id}=PASS",
                    "--evidence", f"{check_id}={evidence}",
                    "--confirmed", check_id,
                ]
            reviewed = self.run_mpa(*review_arguments, "--artifact", "basic_review=" + str(basic_report_fixture(project)))
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr or reviewed.stdout)

            to_publish = self.run_mpa("transition", "--work-root", str(base), "--run-id", "conv")
            self.assertEqual(to_publish.returncode, 0, to_publish.stderr or to_publish.stdout)
            self.assertEqual(json.loads(to_publish.stdout)["advanced_to"], "PUBLISH_GITEE")

            waiting = self.run_mpa(
                "handoff",
                "--work-root", str(base),
                "--run-id", "conv",
                "--workflow", "PUBLISH_GITEE",
                "--status", "BLOCKED",
                "--outcome", "TOKEN_REQUIRED",
                "--reason-code", "AUTH.GITEE_TOKEN_MISSING",
            )
            self.assertEqual(waiting.returncode, 0, waiting.stderr or waiting.stdout)
            stuck = self.run_mpa("transition", "--work-root", str(base), "--run-id", "conv")
            self.assertEqual(stuck.returncode, 3)
            self.assertEqual(json.loads(stuck.stdout)["status"], "WAITING_USER")

            pushed = self.run_mpa(
                "handoff",
                "--work-root", str(base),
                "--run-id", "conv",
                "--workflow", "PUBLISH_GITEE",
                "--status", "PASS",
                "--outcome", "PUSHED",
            )
            self.assertEqual(pushed.returncode, 0, pushed.stderr or pushed.stdout)
            completed = self.run_mpa("transition", "--work-root", str(base), "--run-id", "conv")
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            output = json.loads(completed.stdout)
            self.assertIn("run complete", output["message"])
            self.assertTrue(output["evidence_cleaned"])
            self.assertIsNone(output["run_root"])
            self.assertIn("push", output["external_actions_performed"])
            self.assertFalse((base / ".mindplus-agent" / "runs" / "conv").exists())


def sample_spec(mode: str = "UPLOAD") -> dict:
    return {
        "schema_version": "mindplus-agent.extension-spec/v1",
        "identity": {
            "id": "demo",
            "author": "tester",
            "version": "1.0.0",
            "compatibility_id": "tester-demo-thirdex",
        },
        "mode": mode,
        "blocks": [
            {
                "opcode": "initDemo",
                "block_type": "COMMAND",
                "message_id": "gui.blocklyText.demo.initDemo",
                "parameters": [],
                "generator_claim": "generator.addFunction('demoInit')",
            },
            {
                "opcode": "setMode",
                "block_type": "COMMAND",
                "message_id": "gui.blocklyText.demo.setMode",
                "parameters": [{"field": "dropdown", "name": "MODE"}],
                "generator_claim": "generator.addCode(...)",
            },
        ],
        "dependencies": [],
        "devices": [],
        "assets": [],
        "style": {"color1": "#00B0F0"},
        "readme_claims": [],
        "review_profile": "BASIC",
    }


class SpecToInventoryTests(unittest.TestCase):
    def test_maps_spec_and_feeds_shared_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec_path = base / "extension-spec.json"
            write_json(spec_path, sample_spec())
            inventory_path = base / "spec-inventory.json"
            adapted = run_switch_script(
                "spec_to_inventory.py",
                "--spec", str(spec_path),
                "--output", str(inventory_path),
            )
            self.assertEqual(adapted.returncode, 0, adapted.stderr or adapted.stdout)
            inventory = json.loads(adapted.stdout)
            self.assertEqual(inventory["status"], "PASS")
            self.assertEqual(inventory["candidates"], [{"mode": "UPLOAD", "evidence": "extension-spec.mode"}])
            self.assertEqual(
                inventory["identity"],
                {
                    "id": "demo",
                    "canonical_v2_id": "demo",
                    "expected_compatibility_id": "tester-demo-thirdex",
                },
            )
            self.assertEqual(inventory["v1_entry_inventory"]["UPLOAD"]["block_functions"], ["initDemo", "setMode"])
            self.assertEqual(inventory["v1_entry_inventory"]["UPLOAD"]["declared_color1"], "#00B0F0")
            features = inventory["reference_features_by_mode"]["UPLOAD"]
            for expected in ("field-dropdown", "add-function", "inline-code"):
                self.assertIn(expected, features)

            selected = run_switch_script(
                "select_reference_topics.py",
                "--inventory", str(inventory_path),
                "--active-root", str(SWITCH_REFERENCES / "generated"),
                "--mode", "UPLOAD",
            )
            self.assertEqual(selected.returncode, 0, selected.stderr or selected.stdout)
            selection = json.loads(selected.stdout)
            self.assertEqual(selection["status"], "PASS")
            self.assertIn("field-dropdown", selection["observed_features"])

    def test_python_dependencies_map_to_requirement_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = sample_spec("PYTHON_BLOCK")
            spec["dependencies"] = [{"name": "dflib", "requirement": "dflib==1.0.0"}]
            spec_path = base / "extension-spec.json"
            write_json(spec_path, spec)
            adapted = run_switch_script("spec_to_inventory.py", "--spec", str(spec_path))
            self.assertEqual(adapted.returncode, 0, adapted.stderr or adapted.stdout)
            inventory = json.loads(adapted.stdout)
            self.assertEqual(
                inventory["python_dependency_inventory"]["expected_requirement_lines"],
                ["dflib==1.0.0"],
            )

    def test_missing_field_blocks_instead_of_inferring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = sample_spec()
            del spec["identity"]
            spec_path = base / "extension-spec.json"
            write_json(spec_path, spec)
            adapted = run_switch_script("spec_to_inventory.py", "--spec", str(spec_path))
            self.assertEqual(adapted.returncode, 2)
            output = json.loads(adapted.stdout)
            self.assertEqual(output["status"], "BLOCKED")
            self.assertIn("SPEC_FIELD_MISSING", output["error"])


class DeviceDictionaryTests(unittest.TestCase):
    def mini_project(self, base: Path, support_devices: dict) -> tuple[Path, Path]:
        project = base / "ext2-ul-project"
        extension = project / "extension"
        (extension / "public").mkdir(parents=True)
        (extension / "locales").mkdir(parents=True)
        write_json(
            extension / "public" / "config.json",
            {
                "id": "demo",
                "version": "1.0.0",
                "name": {"zh-cn": "示例", "en": "Demo"},
                "description": {"zh-cn": "", "en": ""},
                "author": "tester",
                "compatibilityId": "tester-demo-thirdex",
                "cover": "",
                "isDevice": False,
                "sku": "",
                "main": "main.js",
                "mode": "upload",
                "libraryConfig": [],
                "meta": {"runtimeVersion": ""},
                "supportDevices": support_devices,
            },
        )
        (extension / "index.js").write_text("export default {};", encoding="utf-8")
        (extension / "func.js").write_text("export default class Func {};", encoding="utf-8")
        write_json(extension / "locales" / "en.json", {})
        write_json(extension / "locales" / "zh-cn.json", {})
        inventory = base / "inventory.json"
        write_json(
            inventory,
            {
                "identity": {
                    "id": "demo",
                    "canonical_v2_id": "demo",
                    "expected_compatibility_id": "tester-demo-thirdex",
                }
            },
        )
        return project, inventory

    def check_findings(self, base: Path, support_devices: dict) -> list[str]:
        project, inventory = self.mini_project(base, support_devices)
        completed = run_switch_script(
            "check_converted_extension.py",
            "--project-root", str(project),
            "--inventory", str(inventory),
            "--mode", "UPLOAD",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        return [finding["code"] for finding in json.loads(completed.stdout)["findings"]]

    def test_unknown_device_id_is_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codes = self.check_findings(Path(directory), {"dev-DFRobot-notABoard": "^0.0.1"})
            self.assertIn("CONFIG_DEVICE_ID_UNKNOWN", codes)

    def test_known_device_id_passes_dictionary_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codes = self.check_findings(Path(directory), {"dev-DFRobot-arduinoUno": "^0.0.1"})
            self.assertNotIn("CONFIG_DEVICE_ID_UNKNOWN", codes)

    def test_bad_support_arch_format_is_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, inventory = self.mini_project(base, {"dev-DFRobot-arduinoUno": "^0.0.1"})
            config_path = project / "extension" / "public" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            del config["supportDevices"]
            config["supportArch"] = ["Arduino AVR"]
            write_json(config_path, config)
            completed = run_switch_script(
                "check_converted_extension.py",
                "--project-root", str(project),
                "--inventory", str(inventory),
                "--mode", "UPLOAD",
            )
            codes = [finding["code"] for finding in json.loads(completed.stdout)["findings"]]
            self.assertIn("CONFIG_SUPPORT_ARCH_FORMAT_INVALID", codes)

    def test_architecture_support_arch_passes_dictionary_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, inventory = self.mini_project(base, {"dev-DFRobot-arduinoUno": "^0.0.1"})
            config_path = project / "extension" / "public" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            del config["supportDevices"]
            config["supportArch"] = ["arduino:avr"]
            write_json(config_path, config)
            completed = run_switch_script(
                "check_converted_extension.py",
                "--project-root", str(project),
                "--inventory", str(inventory),
                "--mode", "UPLOAD",
            )
            codes = [finding["code"] for finding in json.loads(completed.stdout)["findings"]]
            self.assertNotIn("CONFIG_SUPPORT_ARCH_FORMAT_INVALID", codes)


def run_gitee(script_args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("GITEE_TOKEN", None)
    env.pop("GITEE_ACCESS_TOKEN", None)
    # Neutralize a real ~/.gitee-token on the test machine; tests opt in explicitly.
    env["GITEE_TOKEN_FILE"] = str(Path(tempfile.gettempdir()) / "no-such-gitee-token-file")
    # Clearing env vars and redirecting the token file is not enough on Windows:
    # resolve_token() then falls back to Windows Credential Manager, so a machine that
    # has a stored Gitee credential would let the gate legitimately pass. Reset only the
    # credential-helper list (keeping user.name/user.email available for commit tests).
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "credential.helper"
    env["GIT_CONFIG_VALUE_0"] = ""
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "gitee_publish.py"), *script_args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


def make_preflight(project: Path, handoff_path: Path, out_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GITEE_TOKEN"] = "test-token-not-for-network"
    env.pop("GITEE_ACCESS_TOKEN", None)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "prepare_gitee_publish.py"),
         "--project-root", str(project), "--review-handoff", str(handoff_path),
         "--output", str(out_path)],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


def publish_fixture(base: Path, authorized: bool = True) -> tuple[Path, Path, Path]:
    project = base / "ext2-ul-project"
    extension = project / "extension"
    (extension / "public").mkdir(parents=True)
    (project / "node_modules" / "somepkg").mkdir(parents=True)
    (extension / "public" / "config.json").write_text("{}", encoding="utf-8")
    (extension / "index.js").write_text("export default {};", encoding="utf-8")
    (project / "node_modules" / "somepkg" / "pkg.js").write_text("module.exports=1;", encoding="utf-8")
    handoff_path = base / "handoff.json"
    write_json(handoff_path, basic_handoff(project, authorized=authorized))
    preflight_path = base / "publish-preflight.json"
    preflight = make_preflight(project, handoff_path, preflight_path)
    assert preflight.returncode == 0, preflight.stderr or preflight.stdout
    return project, handoff_path, preflight_path


FAKE_TOKEN = "test-token-not-for-network"


class MpaEvidenceTests(unittest.TestCase):
    def test_mpa_start_hides_run_directory(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows hidden attribute only")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            spec = base / "spec.json"
            spec.write_text("{}", encoding="utf-8")
            completed = run_script("mpa.py", 
                "start", "--goals", "CREATE",
                "--project-root", str(base / "ext2-ul-project"),
                "--extension-spec", str(spec),
                "--work-root", str(base), "--run-id", "hidden1",
                "--auth", "local_write",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            run_root = Path(json.loads(completed.stdout)["run_root"])
            attributes = os.stat(run_root).st_file_attributes
            self.assertTrue(attributes & 0x2)  # FILE_ATTRIBUTE_HIDDEN

    def test_mpa_keep_evidence_retains_completed_run_and_clean_removes_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "ext2-ul-v2"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            evidence = base / "ev.json"
            evidence.write_text("{}", encoding="utf-8")
            started = run_script("mpa.py",
                "start", "--goals", "REVIEW",
                "--project-root", str(project),
                "--work-root", str(base), "--run-id", "rev1",
                "--keep-evidence",
            )
            self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
            handoff_args = ["handoff", "--work-root", str(base), "--run-id", "rev1",
                "--workflow", "REVIEW_EXISTING", "--status", "PASS",
                "--outcome", "REVIEWED_BASIC",
                "--check", "builder_build=PASS", "--evidence", f"builder_build={evidence}"]
            for check_id in sorted(BASIC_CHECKS - {"builder_build"}):
                handoff_args += ["--check", f"{check_id}=PASS", "--evidence", f"{check_id}={evidence}",
                                 "--confirmed", check_id]
            written = run_script("mpa.py", *handoff_args, "--artifact", "basic_review=" + str(basic_report_fixture(project)))
            self.assertEqual(written.returncode, 0, written.stderr or written.stdout)
            completed = run_script("mpa.py",
                "transition", "--work-root", str(base), "--run-id", "rev1", "--keep-evidence",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertTrue(json.loads(completed.stdout)["evidence_cleaned"] is False)
            self.assertTrue((base / ".mindplus-agent" / "runs" / "rev1" / "run.json").is_file())

            cleaned = run_script("mpa.py", "clean", "--work-root", str(base), "--run-id", "rev1")
            report = json.loads(cleaned.stdout)["report"]
            self.assertTrue(report[0]["removed"])
            self.assertFalse((base / ".mindplus-agent" / "runs" / "rev1").exists())

    def _convert_run_with_keep(self, base: Path) -> Path:
        v1 = base / "v1"
        v1.mkdir()
        (v1 / "config.json").write_text("{}", encoding="utf-8")
        evidence = base / "record" / "conversion-check.json"
        evidence.parent.mkdir()
        evidence.write_text("{}", encoding="utf-8")
        started = run_script("mpa.py", 
            "start",
            "--goals", "CONVERT,REVIEW,PUBLISH",
            "--project-root", str(base / "ext2-ul-v2"),
            "--v1-source", str(v1),
            "--work-root", str(base),
            "--run-id", "conv",
            "--auth", "local_write", "--auth", "commit", "--auth", "push",
            "--keep-evidence",
        )
        self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
        return evidence


class GiteePublishTests(unittest.TestCase):
    def test_every_stage_requires_token_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, _, preflight = publish_fixture(base)
            for stage_args in (
                ["plan"],
                ["commit", "--message", "m"],
                ["remote", "--owner", "o", "--repo-name", "r"],
                ["push"],
            ):
                completed = run_gitee([*stage_args, "--preflight", str(preflight), "--state-dir", str(base / "state")])
                self.assertEqual(completed.returncode, 3, completed.stderr or completed.stdout)
                output = json.loads(completed.stdout)
                self.assertEqual(output["reason_code"], "AUTH.GITEE_TOKEN_MISSING", stage_args)
                self.assertIn("Nothing was read or modified", output["message"])

    def test_plan_and_commit_with_fake_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, _, preflight = publish_fixture(base)
            state = base / "state"
            env = {"GITEE_TOKEN": FAKE_TOKEN}
            planned = run_gitee(["plan", "--preflight", str(preflight), "--state-dir", str(state)], env_extra=env)
            self.assertEqual(planned.returncode, 0, planned.stderr or planned.stdout)
            plan = json.loads(planned.stdout)
            self.assertEqual(plan["status"], "PASS")
            plan_data = json.loads(Path(plan["plan_file"]).read_text(encoding="utf-8"))
            planned_paths = [entry["path"] for entry in plan_data["manifest"]]
            self.assertIn("extension/public/config.json", planned_paths)
            self.assertFalse(any(path.startswith("node_modules") for path in planned_paths))

            committed = run_gitee(
                ["commit", "--preflight", str(preflight), "--state-dir", str(state),
                 "--message", "Publish demo", "--author-name", "Tester", "--author-email", "t@example.com"],
                env_extra=env,
            )
            self.assertEqual(committed.returncode, 0, committed.stderr or committed.stdout)
            commit_out = json.loads(committed.stdout)
            self.assertFalse(commit_out["reused_existing_commit"])
            tracked = subprocess.run(
                ["git", "-C", str(project), "ls-files"], text=True, capture_output=True, check=False,
            ).stdout.splitlines()
            self.assertIn("extension/public/config.json", tracked)
            self.assertFalse(any(path.startswith("node_modules") for path in tracked))

            outputs = planned.stdout + committed.stdout + (state / "publish-plan.json").read_text(encoding="utf-8") + (state / "publish-commit.json").read_text(encoding="utf-8")
            self.assertNotIn(FAKE_TOKEN, outputs)

    def test_commit_rejects_plan_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, _, preflight = publish_fixture(base)
            state = base / "state"
            env = {"GITEE_TOKEN": FAKE_TOKEN}
            planned = run_gitee(["plan", "--preflight", str(preflight), "--state-dir", str(state)], env_extra=env)
            self.assertEqual(planned.returncode, 0, planned.stderr or planned.stdout)
            (project / "extension" / "new-file.js").write_text("// new", encoding="utf-8")
            committed = run_gitee(
                ["commit", "--preflight", str(preflight), "--state-dir", str(state), "--message", "m"],
                env_extra=env,
            )
            self.assertEqual(committed.returncode, 2)
            self.assertEqual(json.loads(committed.stdout)["reason_code"], "REVIEW.HANDOFF_INVALID")

    def test_plan_stops_on_credential_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, handoff_path, preflight = publish_fixture(base)
            # The secret must be part of the reviewed content: add it, then re-review and re-preflight.
            (project / "extension" / "notes.js").write_text('const GITEE_TOKEN = "abcdef123456789";', encoding="utf-8")
            write_json(handoff_path, basic_handoff(project, authorized=True))
            refreshed = make_preflight(project, handoff_path, preflight)
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr or refreshed.stdout)
            planned = run_gitee(
                ["plan", "--preflight", str(preflight), "--state-dir", str(base / "state")],
                env_extra={"GITEE_TOKEN": FAKE_TOKEN},
            )
            self.assertEqual(planned.returncode, 2)
            output = json.loads(planned.stdout)
            self.assertEqual(output["reason_code"], "SECURITY.CREDENTIAL_MATERIAL_FOUND")
            self.assertTrue(output["secret_findings"])

    def test_remote_create_requires_authorization_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, _, preflight = publish_fixture(base, authorized=True)  # commit/push true, create_repository false
            state = base / "state"
            env = {"GITEE_TOKEN": FAKE_TOKEN}
            run_gitee(["plan", "--preflight", str(preflight), "--state-dir", str(state)], env_extra=env)
            run_gitee(
                ["commit", "--preflight", str(preflight), "--state-dir", str(state), "--message", "m",
                 "--author-name", "T", "--author-email", "t@example.com"],
                env_extra=env,
            )
            completed = run_gitee(
                ["remote", "--preflight", str(preflight), "--state-dir", str(state),
                 "--owner", "o", "--repo-name", "r", "--create", "--private", "--description", "d"],
                env_extra=env,
            )
            self.assertEqual(completed.returncode, 3)
            output = json.loads(completed.stdout)
            self.assertEqual(output["reason_code"], "AUTH.CREATE_REPOSITORY_NOT_AUTHORIZED")

    def test_askpass_shim_answers_username_and_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sys.path.insert(0, str(SCRIPTS))
            from gitee_publish import write_askpass_shim
            shim = write_askpass_shim(Path(directory))
            env = dict(os.environ)
            env["GITEE_TOKEN"] = FAKE_TOKEN
            env["GITEE_AUTH_USER"] = "someuser"
            if os.name == "nt":
                argv = lambda prompt: ["cmd", "/c", str(shim), prompt]
            else:
                argv = lambda prompt: [str(shim), prompt]
            password_out = subprocess.run(
                argv("Password for 'https://someuser@gitee.com': "),
                text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(password_out.stdout.strip(), FAKE_TOKEN, password_out.stderr)
            username_out = subprocess.run(
                argv("Username for 'https://gitee.com': "),
                text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(username_out.stdout.strip(), "someuser", username_out.stderr)
            self.assertNotIn(FAKE_TOKEN, shim.read_text(encoding="utf-8", errors="ignore"))

    def test_transport_selection_by_url(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from gitee_publish import auth_environment, is_ssh_url
        self.assertTrue(is_ssh_url("git@gitee.com:o/r.git"))
        self.assertTrue(is_ssh_url("ssh://git@gitee.com/o/r"))
        self.assertFalse(is_ssh_url("https://gitee.com/o/r.git"))
        with tempfile.TemporaryDirectory() as directory:
            ssh_env = auth_environment({"transport": "ssh", "clone_url": "git@gitee.com:o/r.git"}, "t", Path(directory))
            self.assertIn("GIT_SSH_COMMAND", ssh_env)
            self.assertNotIn("GIT_ASKPASS", ssh_env)
            https_env = auth_environment({"transport": "https", "clone_url": "https://gitee.com/o/r.git", "auth_user": "u"}, "t", Path(directory))
            self.assertIn("GIT_ASKPASS", https_env)
            self.assertNotIn("GIT_SSH_COMMAND", https_env)

    def test_create_public_as_public_and_keep_promotion_as_reconciliation(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from gitee_publish import decide_create_privacy
        # A requested-public repository is created public in one call: promoting an
        # existing repository later would hit the owner-only visibility rule.
        self.assertEqual(decide_create_privacy(True, True), (False, True))
        self.assertEqual(decide_create_privacy(True, False), (True, False))
        self.assertEqual(decide_create_privacy(False, True), (False, True))

    def test_commit_whitespace_is_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, handoff_path, preflight = publish_fixture(base)
            # Trailing whitespace inside the reviewed content must not block the commit.
            padded = project / "extension" / "padded.js"
            padded.write_text("const value = 1;   \n", encoding="utf-8")
            write_json(handoff_path, basic_handoff(project, authorized=True))
            refreshed = make_preflight(project, handoff_path, preflight)
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr or refreshed.stdout)
            state = base / "state"
            env = {"GITEE_TOKEN": FAKE_TOKEN}
            run_gitee(["plan", "--preflight", str(preflight), "--state-dir", str(state)], env_extra=env)
            committed = run_gitee(
                ["commit", "--preflight", str(preflight), "--state-dir", str(state),
                 "--message", "m", "--author-name", "T", "--author-email", "t@example.com"],
                env_extra=env,
            )
            self.assertEqual(committed.returncode, 0, committed.stderr or committed.stdout)
            output = json.loads(committed.stdout)
            self.assertEqual(output["whitespace_check"], "WARN")
            self.assertTrue(output["whitespace_warnings"])


    def test_transport_default_prefers_ssh_then_falls_back(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from gitee_publish import select_transport
        self.assertEqual(select_transport("auto", True), ("ssh", None))
        transport, reason = select_transport("auto", False)
        self.assertEqual(transport, "https")
        self.assertIn("SSH probe failed", reason)
        self.assertEqual(select_transport("ssh", True), ("ssh", None))
        self.assertEqual(select_transport("https", False), ("https", None))
        self.assertEqual(select_transport("https", True), ("https", None))

if __name__ == "__main__":
    unittest.main()
