import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from test_update_and_shadow import updater, packer, archive


class IntegrityTests(unittest.TestCase):
    def asset(self, kind="wb"):
        name = "mindplus-extension-skills-0.2.3-" + ("workbuddy" if kind == "wb" else "universal") + ".zip"
        return {"name": name, "browser_download_url": "https://gitee.com/package.zip",
                "checksum": {"name": name + ".sha256", "browser_download_url": "https://gitee.com/package.zip.sha256"}}

    def test_rate_limited_api_installs_verified_release_from_public_page(self):
        tag = "v0.2.3"
        downloads = updater.RELEASE_PAGE + "download/" + tag + "/"
        for status, kind in ((403, "wb"), (429, "universal")):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "skill"
                root.mkdir()
                updater.unpack(archive(kind, number="0.2.2"), root, (0, 2, 2), kind)
                name = self.asset(kind)["name"]
                path = updater.urlparse(downloads).path
                page = (f'<a href="{path}{name}">ZIP</a>'
                        f'<a href="{path}{name}.sha256">SHA-256</a>').encode()
                data = archive(kind, number="0.2.3")
                checksum = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode()

                def fetch(url, limit):
                    if url.startswith(updater.RELEASES + "?"):
                        raise HTTPError(url, status, "Rate Limit Exceeded", {}, None)
                    if url == updater.RELEASE_PAGE + "latest":
                        return page, updater.RELEASE_PAGE + "tag/" + tag
                    payloads = {downloads + name: data, downloads + name + ".sha256": checksum}
                    return payloads[url], url

                with patch.object(updater, "fetch", side_effect=fetch) as request, \
                     patch.object(updater, "cache_path", return_value=Path(tmp) / "cache"), \
                     patch.object(updater, "backup_path", return_value=Path(tmp) / "previous.zip"):
                    result = updater.update(root, refresh=True)
                self.assertEqual(result["status"], "UPDATED")
                self.assertEqual(result["installed_version"], "0.2.3")
                self.assertTrue(result["sha256_verified"])
                self.assertEqual([call.args[0] for call in request.call_args_list], [
                    updater.RELEASES + "?page=1&per_page=100", updater.RELEASE_PAGE + "latest",
                    downloads + name + ".sha256", downloads + name,
                ])

    def test_updates_both_layouts_and_rechecks_cached_checksum(self):
        for kind in ("wb", "universal"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "skill"
                root.mkdir()
                updater.unpack(archive(kind, number="0.2.2"), root, (0, 2, 2), kind)
                data = archive(kind, number="0.2.3")
                asset = self.asset(kind)
                checksum = (hashlib.sha256(data).hexdigest() + "  " + asset["name"] + "\n").encode()
                with patch.object(updater, "cache_path", return_value=Path(tmp) / "cache"), patch.object(updater, "backup_path", return_value=Path(tmp) / "previous.zip"):
                    updater.store_cache(root, (0, 2, 2), kind, ((0, 2, 3), asset))
                    with patch.object(updater, "download", side_effect=[checksum, data]) as download:
                        result = updater.update(root)
                    self.assertTrue(result["sha256_verified"])
                    self.assertTrue(result["cache_hit"])
                    self.assertEqual(result["installed_version"], "0.2.3")
                    self.assertEqual(download.call_args_list[0].args[0], asset["checksum"]["browser_download_url"])

    def test_bad_checksum_never_installs_or_backs_up(self):
        asset = self.asset()
        for checksum in (b"html error", b"f" * 64 + b"  wrong.zip", b"f" * 64 + b"  " + asset["name"].encode()):
            with self.subTest(checksum=checksum), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                updater.unpack(archive(number="0.2.2"), root, (0, 2, 2), "wb")
                before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                cached = {"remote_version": "0.2.3", "asset": asset}
                with patch.object(updater, "load_cache", return_value=cached), patch.object(updater, "download", side_effect=[checksum, b"corrupt"]), patch.object(updater, "install") as install:
                    with self.assertRaises(updater.IntegrityError):
                        updater.update(root)
                    install.assert_not_called()
                self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_missing_duplicate_and_automatic_source_assets_rejected(self):
        asset = self.asset()
        for assets in ([asset], [asset, asset["checksum"], asset["checksum"]], [{"name": "v0.2.3.zip"}]):
            with self.subTest(assets=assets), self.assertRaises(updater.IntegrityError):
                updater.choose([{"tag_name": "v0.2.3", "assets": assets}], (0, 2, 2), "wb")

    def test_download_bounds_and_redirect_rejection(self):
        for body, length, limit in ((b"12345", "5", 4), (b"12345", None, 4), (b"12", "3", 4)):
            response = Mock()
            response.url = "https://gitee.com/file"
            response.headers = {"Content-Length": length} if length else {}
            response.read.side_effect = io.BytesIO(body).read
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            opener = Mock()
            opener.open.return_value = response
            with patch.object(updater.urllib.request, "build_opener", return_value=opener), self.assertRaises(updater.IntegrityError):
                updater.download(response.url, limit=limit)
        for url in ("https://evil.example/file", "http://gitee.com/file", "https://user:secret@gitee.com/file", "https://gitee.com:8443/file"):
            with self.subTest(url=url), self.assertRaises(updater.IntegrityError):
                updater.ReleaseRedirect().redirect_request(None, None, 302, "", {}, url)

    def test_source_collection_and_checksum_binding(self):
        files = packer.collect_source(Path(__file__).resolve().parents[1])
        self.assertIn("tools/pack_workbuddy.py", files)
        self.assertIn(".workflow/release-workbuddy.yml", files)
        self.assertIn("references/switch/cover-design.md", files)
        self.assertFalse(any(n.startswith(("dist/", ".git/")) for n in files))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            path.write_bytes(b"source")
            self.assertEqual(packer.checksum_file(path).read_text(), hashlib.sha256(b"source").hexdigest() + "  source.zip\n")
