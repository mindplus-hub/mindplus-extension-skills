import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/switch"))
import update_skill as updater
import inventory_v1
import select_reference_topics as selector
sys.path.insert(0, str(ROOT / "tools"))
import pack_workbuddy as packer


def archive(kind="wb", number="0.2.0", wrapper="", extra=None):
    files = {"SKILL.md": "new skill", "VERSION": number, "scripts/mpa.py": "pass\n"}
    files["references/topic.md" if kind == "wb" else "references/nested/topic.md"] = "topic"
    files.update(extra or {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, value in files.items():
            z.writestr(wrapper + name, value)
    return buf.getvalue()


class UpdateTests(unittest.TestCase):
    def test_release_selection(self):
        releases = [{"tag_name": "0.2.0", "assets": [
            {"name": "mindplus-agent-skill-0.2.0-workbuddy.zip"}, {"name": "0.2.0.zip"}]},
            {"tag_name": "0.3.0-rc1", "assets": []}]
        self.assertTrue(updater.choose(releases, (0, 1, 0), "wb")[1]["name"].endswith("workbuddy.zip"))
        self.assertEqual(updater.choose(releases, (0, 1, 0), "universal")[1]["name"], "0.2.0.zip")
        self.assertIsNone(updater.choose(releases, (0, 2, 0), "wb"))

    def test_layout_ignores_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            updater.unpack(archive(), root, (0, 2, 0), "wb")
            path = root / "scripts/__pycache__/nested/file.pyc"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"cache")
            self.assertEqual(updater.variant(root), "wb")

    def test_universal_source_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            updater.unpack(archive("universal", wrapper="repo-0.2.0/"), root, (0, 2, 0), "universal")
            self.assertTrue((root / "SKILL.md").is_file())

    def test_reject_invalid_packages(self):
        for data in [archive(extra={"../outside": "bad"}), archive(extra={"scripts/a/b.py": "pass"}),
                     archive(number="0.9.0"), archive(extra={"scripts/MPA.py": "pass"})]:
            with self.subTest(), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    updater.unpack(data, Path(tmp), (0, 2, 0), "wb")

    def test_install_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill"
            root.mkdir()
            updater.unpack(archive(number="0.1.0"), root, (0, 1, 0), "wb")
            (root / "local.txt").write_text("preserve")
            backup = Path(updater.install(root, archive(), (0, 2, 0), "wb"))
            self.assertEqual(updater.version(root), (0, 2, 0))
            self.assertEqual((backup / "local.txt").read_text(), "preserve")

    def test_failure_before_switch_preserves_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill"
            root.mkdir()
            updater.unpack(archive(number="0.1.0"), root, (0, 1, 0), "wb")
            with self.assertRaises(ValueError):
                updater.install(root, archive(number="0.9.0"), (0, 2, 0), "wb")
            self.assertEqual(updater.version(root), (0, 1, 0))

    def test_switch_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill"
            root.mkdir()
            updater.unpack(archive(number="0.1.0"), root, (0, 1, 0), "wb")
            original = Path.rename
            def rename(path, target):
                if path.name.startswith("skill-update-"):
                    raise OSError("simulated switch failure")
                return original(path, target)
            with patch.object(Path, "rename", rename), self.assertRaises(OSError):
                updater.install(root, archive(), (0, 2, 0), "wb")
            self.assertEqual(updater.version(root), (0, 1, 0))


class ShadowTests(unittest.TestCase):
    def test_normal_and_string_load_symbol_reference_in_both_modes(self):
        for shadow in ("normal", "string"):
            features = inventory_v1.common_features(f'//% NM.shadow="{shadow}" NM.defl="obj"', "", [])
            self.assertIn("field-string", features)
            for mode in ("UPLOAD", "PYTHON_BLOCK"):
                with self.subTest(shadow=shadow, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    inventory = Path(tmp) / "inventory.json"
                    inventory.write_text(json.dumps({"status": "PASS", "candidates": [{"mode": mode}],
                                                     "reference_features": sorted(features)}))
                    result = selector.select(inventory, ROOT / "references/switch/generated", mode)
                    topics = {x["topic_id"] for x in result["topics"]}
                    self.assertIn("shared.field.string", topics)
                    self.assertIn("shared.block.special", topics)


class ReleasePackagingTests(unittest.TestCase):
    def test_file_credential_without_token_environment(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            token = root / "release-token"
            token.write_text("fixture-secret\n", encoding="utf-8")
            self.assertEqual(packer.release_token(root / "checkout", token), "fixture-secret")
            with patch.object(packer.Path, "home", return_value=root):
                token.rename(root / ".gitee-token")
                self.assertEqual(packer.release_token(root / "checkout"), "fixture-secret")

    def test_explicit_invalid_credential_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MP_RELEASE_TOKEN": "another-secret"}):
            with self.assertRaises(packer.PackageError):
                packer.release_token(Path(tmp) / "checkout", Path(tmp) / "missing")
            token = Path(tmp) / "checkout" / "token"
            with self.assertRaises(packer.PackageError):
                packer.release_token(Path(tmp) / "checkout", token)

    def test_adapter_preserves_fstrings_without_unparse(self):
        adapter = packer.Adapter({"scripts/switch/init_run.py": b""})
        source = '''# 保留注释
ctx = {"path": "example"}
message = f"路径：{ctx['path']}"
command = f"python {root}/scripts/switch/init_run.py"
'''
        with patch.object(packer.ast, "unparse", side_effect=AssertionError("must not unparse")):
            result = adapter.python(source, "scripts/example.py")
        self.assertIn("# 保留注释", result)
        self.assertIn('message = f"路径：{ctx[\'path\']}"', result)
        namespace = {"root": "/skill"}
        exec(result, namespace)
        self.assertEqual(namespace["message"], "路径：example")
        self.assertEqual(namespace["command"], "python /skill/scripts/switch__init_run.py")

    def test_marketplace_copy_is_separate_from_skill_frontmatter(self):
        info = packer.load_metadata(ROOT / "release-info.json", False)
        info.update(marketplace_introduction="测试市场介绍", marketplace_prompts="示例提问一\n示例提问二")
        text = packer.marketplace_copy(info)
        self.assertIn("## 介绍", text)
        self.assertIn(info["marketplace_introduction"], text)
        self.assertIn("## 试试这样问我", text)
        for prompt in info["marketplace_prompts"].splitlines():
            self.assertIn(prompt, text)
        output, _ = packer.build_files(packer.collect(ROOT), info, False)
        self.assertNotIn("marketplace-info.md", output)
        self.assertNotIn("marketplace_prompts:", output["SKILL.md"].decode())

    def test_body_preserves_human_notes_and_is_idempotent(self):
        info = {"repository": "https://gitee.com/mind-plus/mindplus-agent-skill", "version": "0.1.2"}
        body = packer.release_body("团队更新说明\n", info, "v0.1.2", "a" * 64, "package.zip")
        self.assertTrue(body.startswith("团队更新说明\n"))
        self.assertEqual(packer.release_body(body, info, "v0.1.2", "a" * 64, "package.zip"), body)
        with self.assertRaises(packer.PackageError):
            packer.release_body("<!-- mindplus-pack:start -->", info, "v0.1.2", "", "package.zip")

    def test_package_excludes_development_tools_and_workflow(self):
        files = packer.collect(ROOT)
        self.assertNotIn("tools/pack_workbuddy.py", files)
        self.assertNotIn(".workflow/release-workbuddy.yml", files)
        self.assertNotIn("release-info.json", files)
        info = packer.load_metadata(ROOT / "release-info.json", False)
        self.assertEqual(files["VERSION"].decode().strip(), info["version"])
        output, _ = packer.build_files(files, info, False)
        packer.validate_layout(output)
        self.assertIn(f'version: "{info["version"]}"', output["SKILL.md"].decode())

    def test_release_tag_mismatch_stops_before_git(self):
        with patch.object(packer.subprocess, "run") as git:
            with self.assertRaises(packer.PackageError):
                packer.release_commit(ROOT, {"version": "0.1.2"}, "v0.1.1")
            git.assert_not_called()

    def test_missing_token_and_preview_stop_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(packer.Path, "home", return_value=Path(tmp)), patch.dict(os.environ, {}, clear=True), patch.object(packer, "ReleaseAPI") as api:
            for result in ({"status": "PASS", "preview": True}, {"status": "PASS", "preview": False}):
                with self.assertRaises(packer.PackageError):
                    packer.publish(result, ROOT, ROOT / "release-info.json", "v0.1.2")
            api.assert_not_called()

    def publication_fixture(self, root):
        source = root / "skill"
        (source / "scripts").mkdir(parents=True)
        (source / "SKILL.md").write_text("skill")
        (source / "scripts/mpa.py").write_text("pass")
        info = packer.load_metadata(ROOT / "release-info.json", False)
        (source / "VERSION").write_text(info["version"])
        metadata = source / "release-info.json"
        packer.write_json(metadata, info)
        zip_path = root / f'mindplus-agent-skill-{info["version"]}-workbuddy.zip'
        zip_path.write_bytes(b"fixture-archive")
        report = root / "report.json"
        packer.write_json(report, {"metadata": info, "source_files": {n: packer.sha(d) for n, d in packer.collect(source).items()}})
        result = {"status": "PASS", "preview": False, "zip": str(zip_path), "report": str(report), "zip_sha256": packer.sha(zip_path.read_bytes())}
        return source, metadata, info, result

    def test_reuse_attachment_preserves_release_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, metadata, info, result = self.publication_fixture(Path(tmp))
            tag = "v" + info["version"]
            release = {"id": 1, "tag_name": tag, "name": "团队标题", "body": "团队说明", "prerelease": False}
            api = Mock()
            api.attachments.return_value = [{"name": Path(result["zip"]).name}]
            def request(method, path, payload=None, **kwargs):
                if method == "PATCH":
                    release.update(payload)
                return dict(release)
            api.request.side_effect = request
            with patch.dict(os.environ, {"MP_RELEASE_TOKEN": "test-secret"}), patch.object(packer, "ReleaseAPI", return_value=api), patch.object(packer, "release_commit", return_value="a" * 40):
                published = packer.publish(result, source, metadata, tag)
                self.assertTrue(published["reused_attachment"])
                self.assertEqual(release["name"], "团队标题")
                self.assertTrue(release["body"].startswith("团队说明"))
                self.assertFalse(any(call.args[0] == "POST" for call in api.request.call_args_list))
                api.request.reset_mock()
                packer.publish(result, source, metadata, tag)
                self.assertFalse(any(call.args[0] != "GET" for call in api.request.call_args_list))

    def test_new_release_uploads_then_patches_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, metadata, info, result = self.publication_fixture(Path(tmp))
            tag = "v" + info["version"]
            state = {}
            api = Mock()
            api.attachments.return_value = []
            def request(method, path, payload=None, **kwargs):
                if method == "POST" and path == "/releases":
                    state.update(payload, id=7)
                elif method == "POST":
                    self.assertEqual(path, "/releases/7/attach_files")
                    return {"name": Path(result["zip"]).name}
                elif method == "PATCH":
                    state.update(payload)
                return dict(state) if state else None
            api.request.side_effect = request
            with patch.dict(os.environ, {"MP_RELEASE_TOKEN": "test-secret"}), patch.object(packer, "ReleaseAPI", return_value=api), patch.object(packer, "release_commit", return_value="a" * 40):
                published = packer.publish(result, source, metadata, tag)
            self.assertFalse(published["reused_attachment"])
            self.assertIn("mindplus-pack:start", state["body"])
            api.verify_attachment.assert_called_once()

    def test_mismatched_attachment_does_not_edit_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, metadata, info, result = self.publication_fixture(Path(tmp))
            tag = "v" + info["version"]
            api = Mock()
            api.request.return_value = {"id": 1, "tag_name": tag, "prerelease": False}
            api.attachments.return_value = [{"name": Path(result["zip"]).name}]
            api.verify_attachment.side_effect = packer.PackageError("different bytes")
            with patch.dict(os.environ, {"MP_RELEASE_TOKEN": "test-secret"}), patch.object(packer, "ReleaseAPI", return_value=api), patch.object(packer, "release_commit", return_value="a" * 40):
                with self.assertRaises(packer.PackageError):
                    packer.publish(result, source, metadata, tag)
            self.assertFalse(any(call.args[0] != "GET" for call in api.request.call_args_list))


if __name__ == "__main__":
    unittest.main()
