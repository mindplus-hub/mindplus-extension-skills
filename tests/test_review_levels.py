import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_workflow import basic_report_fixture, basic_handoff, run_script, run_switch_script, write_json, FAKE_TOKEN
from check_basic_review import verify_file, package_facts, EVIDENCE_CHECKS
from check_lite_review import match_entries, collision_folder, inspect, verify_selection
from route_workflow import route, read_json, REGISTRY_PATH
from validate_handoff import validate
import gitee_publish as publish


class ReviewLevelsTests(unittest.TestCase):
    def test_lite_author_and_id_are_identity_not_names_or_gitee_owner(self):
        query = {"author": "Alice", "id": "sensor", "name": "Sensor"}
        entries = [{"author": "Alice", "id": "sensor"}, {"author": "Bob", "id": "sensor"},
                   {"author": "Alice", "id": "other", "name": "Sensor"},
                   {"id": "sensor", "name": "Sensor", "html_url": "https://gitee.com/Alice/sensor"}]
        self.assertEqual([x["identity"] for x in match_entries(entries, query)],
                         ["SAME_LIBRARY", "ID_COLLISION", "RELATED_CANDIDATE", "REPOSITORY_CONFIG_UNVERIFIED"])

    def test_lite_suffix_is_idempotent_and_preserves_all_mode_prefixes(self):
        for mode in ("rt", "ul", "py", "mpy"):
            name = f"ext2-{mode}-sensor"
            self.assertEqual(collision_folder(name, "Alice"), name + "-Alice")
            self.assertEqual(collision_folder(name + "-Alice", "Alice"), name + "-Alice")
            self.assertEqual(collision_folder(name, "小明", "XiaoMing"), name + "-XiaoMing")
        with self.assertRaises(ValueError):
            collision_folder("ext2-ul-sensor", "小明")

    def test_lite_network_failure_and_pagination_do_not_claim_absence(self):
        def failure(url):
            raise OSError("offline")
        self.assertEqual(inspect("ul", "extension", {"id": "sensor"}, failure)["status"], "UNVERIFIED")
        def incomplete(url):
            return ([{}] * 100 if "gitee.com" in url else []), "a" * 64
        self.assertEqual(inspect("ul", "extension", {"id": "sensor"}, incomplete)["status"], "UNVERIFIED")
        with self.assertRaises(ValueError):
            inspect("py", "device", {}, incomplete)

    def test_lite_repository_discovery_uses_the_publication_topic(self):
        seen = []
        def complete(url):
            seen.append(url)
            return [], "a" * 64
        report = inspect("ul", "extension", {"id": "sensor"}, complete)
        self.assertEqual(report["status"], "CANDIDATES_READY")
        topic_sources = [source for source in report["sources"] if "gitee.com" in source["url"]]
        self.assertEqual(topic_sources[0]["scope"], {"type": "topic", "name": "MindPlus-Ext2"})
        self.assertIn("/search/repositories?q=MindPlus-Ext2", seen[1])

    def test_lite_selection_cannot_waive_collision_or_fork(self):
        from hash_project import file_digest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "candidates.json"
            report = {"status": "CANDIDATES_READY", "query": {"author": "Alice", "id": "sensor"},
                      "sources": [{"candidates": [{"identity": "ID_COLLISION"}]}]}
            write_json(report_path, report)
            project = root / "ext2-ul-sensor-Alice"
            selection = {"schema_version": "mindplus.review-lite-selection/v1", "status": "PASS",
                         "project_root": str(project), "candidate_report": str(report_path),
                         "candidate_sha256": file_digest(report_path), "decision": "NO_DUPLICATE",
                         "comparison": "test", "source_decision": "test"}
            with self.assertRaises(ValueError):
                verify_selection(project, selection)
            selection.update(decision="ID_COLLISION_RENAMED", original_folder="ext2-ul-sensor", author="Alice")
            verify_selection(project, selection)
            report["sources"][0]["candidates"][0]["identity"] = "SAME_LIBRARY"
            write_json(report_path, report)
            selection["candidate_sha256"] = file_digest(report_path)
            with self.assertRaises(ValueError):
                verify_selection(project, selection)
            selection.update(decision="FORK_EXISTING", original_repository="https://gitee.com/mind-plus/example",
                             repository="https://gitee.com/test/example", fork_verified=True)
            verify_selection(project, selection)
            selection["fork_verified"] = "false"
            with self.assertRaises(ValueError):
                verify_selection(project, selection)

    def test_unsupported_profile_and_publish_cannot_route_around_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "config.json").write_text("{}")
            request = {"goals": ["PUBLISH"], "paths": {"project_root": str(project)}, "authorizations": {"commit": True, "push": True}}
            registry = read_json(REGISTRY_PATH)
            self.assertEqual(route(request, registry)["workflows"], ["REVIEW_EXISTING", "PUBLISH_GITEE"])
            for profile in ("FULL", "HOST_READY"):
                self.assertEqual(route(dict(request, review_profile=profile), registry)["reason_code"], "ROUTE.REVIEW_PROFILE_UNSUPPORTED")

    def test_basic_rejects_each_missing_gate_or_stale_artifact_or_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            report_path = basic_report_fixture(project)
            original = json.loads(report_path.read_text())
            verify_file(project, report_path)
            for check in EVIDENCE_CHECKS:
                report = copy.deepcopy(original)
                report["checks"][check]["result"] = "NOT_RUN"
                write_json(report_path, report)
                with self.assertRaises(ValueError, msg=check):
                    verify_file(project, report_path)
            write_json(report_path, original)
            Path(original["artifact"]["path"]).write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_file(project, report_path)
            report_path = basic_report_fixture(project)
            (project / "new.js").write_text("source drift")
            with self.assertRaises(ValueError):
                verify_file(project, report_path)

    def test_zip_exact_boundary_and_unsafe_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "extension.zip"
            with zipfile.ZipFile(package, "w") as z:
                z.writestr("main.js", "")
                z.writestr("config.json", "{}")
            overhead = package.stat().st_size
            with zipfile.ZipFile(package, "w") as z:
                z.writestr("main.js", b"x" * (5_000_000 - overhead))
                z.writestr("config.json", "{}")
            self.assertEqual(package_facts(package)["size_bytes"], 5_000_000)
            with package.open("ab") as f:
                f.write(b"x")
            with self.assertRaises(ValueError):
                package_facts(package)
            with zipfile.ZipFile(package, "w") as z:
                z.writestr("../main.js", "x")
                z.writestr("config.json", "{}")
            with self.assertRaises(ValueError):
                package_facts(package)

    def test_publication_stages_revalidate_basic_before_mutation(self):
        import argparse
        from hash_project import compute_project_hash
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            report = basic_report_fixture(project)
            preflight = Path(tmp) / "preflight.json"
            value = {"status": "PASS", "outcome": "PUBLISH_PREPARE_READY", "project_root": str(project),
                     "project_sha256": compute_project_hash(project)[0], "basic_review": str(report), "authorizations": {"push": True}}
            write_json(preflight, value)
            args = argparse.Namespace(preflight=preflight, state_dir=Path(tmp) / "state")
            with patch.object(publish, "resolve_token", return_value=("test", FAKE_TOKEN)):
                publish.context(args)
                report.unlink()
                with self.assertRaises(publish.StageBlocked) as ctx:
                    publish.context(args)
                self.assertIn("BASIC_NOT_READY", str(ctx.exception.payload))


    def test_basic_cli_refuses_a_report_that_never_passed(self):
        # The CLI used to call verify() directly, so a content-complete report
        # that still read BLOCKED was rewritten to PASS and accepted.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            report_path = basic_report_fixture(project)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["status"] = "BLOCKED"
            write_json(report_path, report)
            output = Path(tmp) / "basic-review.json"
            completed = run_script(
                "check_basic_review.py",
                "--project-root", str(project),
                "--evidence", str(report_path),
                "--output", str(output),
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("has not passed", result["error"])
            self.assertNotEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "PASS")

    def test_switch_log_update_refuses_an_event_that_forges_lines(self):
        # --event is appended as a whole log line; an embedded newline would let a
        # caller inject entries into the run log that Basic later cites as evidence.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.md"
            log.write_text(
                "# MindPlus-Switch Run Log\n\n- current_step: S-1 OPEN_RUN_LOG\n\n"
                "## Checkpoints\n\n- [ ] S2 LOAD_REFERENCES\n",
                encoding="utf-8",
            )
            completed = run_switch_script(
                "update_run_log.py",
                "--log", str(log),
                "--step", "S2",
                "--result", "PASS",
                "--event", "ok\n- [x] S3 forged entry",
            )
            self.assertEqual(completed.returncode, 2, completed.stdout)
            self.assertIn("newlines", json.loads(completed.stdout)["error"])
            self.assertNotIn("forged entry", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
