import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "official_discovery", Path(__file__).resolve().parents[1] / "scripts/switch/fetch_official_reference.py")
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class OfficialDiscoveryTests(unittest.TestCase):
    def lookup(self, batches, page=None):
        output = io.StringIO()
        with patch.object(discovery, "http_get_json", side_effect=batches) as request:
            with contextlib.redirect_stdout(output):
                code = discovery.cmd_list(argparse.Namespace(page=page, search="target"))
            self.request_urls = [call.args[0] for call in request.call_args_list]
        return code, json.loads(output.getvalue()), request.call_count

    def test_full_pagination_finds_later_match(self):
        code, result, calls = self.lookup([[{"path": "other"}] * 100, [{"path": "target"}]])
        self.assertEqual(code, 0)
        self.assertEqual(calls, 2)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["complete"])
        self.assertIsNone(result["next_page"])
        self.assertEqual(result["topic"], "MindPlus-Ext2")
        self.assertIn("/search/repositories?q=MindPlus-Ext2", self.request_urls[0])

    def test_page_cap_is_not_proof_of_absence(self):
        code, result, calls = self.lookup([[{"path": "other"}] * 100] * 10)
        self.assertEqual(code, 0)
        self.assertEqual(calls, 10)
        self.assertEqual(result["count"], 0)
        self.assertFalse(result["complete"])
        self.assertEqual(result["next_page"], 11)

    def test_single_later_page_does_not_cover_the_topic(self):
        _, result, calls = self.lookup([[]], page=11)
        self.assertEqual(calls, 1)
        self.assertTrue(result["reached_end"])
        self.assertFalse(result["complete"])

    def test_invalid_responses_and_network_failures_block(self):
        for response in ({"message": "error"}, [None], discovery.FetchError("unavailable")):
            with self.subTest(response=response):
                code, result, _ = self.lookup([response])
                self.assertNotEqual(code, 0)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertNotIn("repositories", result)

    def test_tree_rejects_a_repository_without_owner(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = discovery.cmd_tree(argparse.Namespace(repo="not-a-full-name", path="", ref="main"))
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["reason_code"], "OFFICIAL_CORPUS.NETWORK")


if __name__ == "__main__":
    unittest.main()
