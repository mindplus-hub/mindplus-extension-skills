import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/switch"))
import update_skill as updater
import inventory_v1
import select_reference_topics as selector


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


if __name__ == "__main__":
    unittest.main()
