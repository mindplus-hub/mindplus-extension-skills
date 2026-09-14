import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "switch"))
import prepare_builder_scaffold as scaffold

class ScaffoldReleaseTests(unittest.TestCase):
    def test_select_numeric_latest_and_no_fallback(self):
        def release(tag, assets=True):
            return {"tag_name": tag, "assets": [{"name": scaffold.ARCHIVE_NAME, "browser_download_url": "https://gitee.com/scaffold.zip"}] if assets else []}
        result = scaffold.select_release([release("v0.0.1"), release("v0.0.10"), release("v0.0.2"), release("v9.0.0-rc1")])
        self.assertEqual(result["release_tag"], "v0.0.10")
        with self.assertRaises(scaffold.ScaffoldError):
            scaffold.select_release([release("v0.0.1"), release("v0.0.2", False)])

    def test_both_layouts_preserve_gitignore_and_verify_digest(self):
        for wrapper in ("", "scaffold/"):
            with self.subTest(wrapper=wrapper), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive = root / "source.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    for name in scaffold.REQUIRED_PATHS:
                        directory = name in {"extension", "scripts", "utils"}
                        z.writestr(wrapper + name + ("/" if directory else ""), b"" if directory else b"new-template")
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                project = root / "ext2-test"
                result = scaffold.extract_checked(archive, project, {"expected_sha256": digest, "release_tag": "v0.0.2"})
                self.assertTrue(result["checksum_verified"])
                self.assertEqual((project / ".gitignore").read_bytes(), b"new-template")
                with self.assertRaises(scaffold.ScaffoldError):
                    scaffold.extract_checked(archive, root / "ext2-bad", {"expected_sha256": "0" * 64})
                self.assertFalse((root / "ext2-bad").exists())
