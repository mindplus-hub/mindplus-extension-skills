import hashlib
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock
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
                project = root / "ext2-ul-test"
                result = scaffold.extract_checked(archive, project, {"expected_sha256": digest, "release_tag": "v0.0.2"})
                self.assertTrue(result["checksum_verified"])
                self.assertEqual((project / ".gitignore").read_bytes(), b"new-template")
                with self.assertRaises(scaffold.ScaffoldError):
                    scaffold.extract_checked(archive, root / "ext2-ul-bad", {"expected_sha256": "0" * 64})
                self.assertFalse((root / "ext2-ul-bad").exists())


class ReleaseChannelTests(unittest.TestCase):
    """发布通道是匿名查询的，被限流时必须给出可复现的恢复路径。"""

    def test_rate_limit_becomes_recovery_hint(self):
        for code in (403, 429):
            with self.subTest(code=code), mock.patch.object(
                scaffold, "download", side_effect=urllib.error.HTTPError("u", code, "Forbidden", None, None)
            ):
                with self.assertRaises(scaffold.ScaffoldError) as caught:
                    scaffold.latest_release()
                message = str(caught.exception)
                self.assertIn(str(code), message)
                self.assertIn("--archive", message)
                self.assertIn("--sha256", message)
                self.assertIn("RECORDED_ONLY", message)

    def test_non_rate_limit_error_is_not_rewritten(self):
        with mock.patch.object(
            scaffold, "download", side_effect=urllib.error.HTTPError("u", 404, "Not Found", None, None)
        ):
            with self.assertRaises(urllib.error.HTTPError):
                scaffold.latest_release()

    def test_published_checksum_attachment_format_is_accepted(self):
        digest = "a" * 64
        release = {
            "tag_name": "v0.0.2",
            "assets": [
                {"name": scaffold.ARCHIVE_NAME, "browser_download_url": "https://gitee.com/scaffold.zip"},
                {"name": scaffold.ARCHIVE_NAME + ".sha256", "browser_download_url": "https://gitee.com/scaffold.zip.sha256"},
            ],
        }
        # sha256sum 文本模式：两个空格（脚本正则接受空格或 * 作为模式标记）
        for body in (f"{digest}  {scaffold.ARCHIVE_NAME}", f"{digest} *{scaffold.ARCHIVE_NAME}"):
            with self.subTest(body=body), mock.patch.object(scaffold, "download", return_value=body.encode("ascii")):
                result = scaffold.select_release([release])
                self.assertEqual(result["expected_sha256"], digest)

    def test_single_space_checksum_attachment_is_rejected(self):
        body = f"{'a' * 64} {scaffold.ARCHIVE_NAME}"
        release = {
            "tag_name": "v0.0.2",
            "assets": [
                {"name": scaffold.ARCHIVE_NAME, "browser_download_url": "https://gitee.com/scaffold.zip"},
                {"name": scaffold.ARCHIVE_NAME + ".sha256", "browser_download_url": "https://gitee.com/scaffold.zip.sha256"},
            ],
        }
        with mock.patch.object(scaffold, "download", return_value=body.encode("ascii")):
            with self.assertRaises(scaffold.ScaffoldError):
                scaffold.select_release([release])
