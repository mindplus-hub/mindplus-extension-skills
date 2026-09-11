import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_workflow import FAKE_TOKEN
import gitee_publish as pub


class RepositoryTopicTests(unittest.TestCase):
    def test_existing_topic_is_read_only(self):
        with patch.object(pub, 'gitee_api', return_value=(200, [{'name': 'MindPlus-Ext2'}])) as api:
            result = pub.ensure_publication_topic('owner', 'repo', FAKE_TOKEN)
        self.assertEqual(result['status'], 'ALREADY_PRESENT')
        self.assertEqual(api.call_count, 1)

    def test_add_is_array_post_and_preserves_existing_topics(self):
        with patch.object(pub, 'gitee_api', side_effect=[(200, [{'name': 'Arduino'}]),
                (201, []), (200, [{'name': 'Arduino'}, {'name': 'MindPlus-Ext2'}])]) as api:
            result = pub.ensure_publication_topic('owner', 'a repo', FAKE_TOKEN)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual([call.args[0] for call in api.call_args_list], ['GET', 'POST', 'GET'])
        self.assertEqual(api.call_args_list[1].kwargs['body'], ['MindPlus-Ext2'])
        self.assertIn('/a%20repo/project_labels', api.call_args_list[1].args[1])
        self.assertNotIn(FAKE_TOKEN, json.dumps(result))

    def test_failed_or_malformed_read_never_writes(self):
        for response in ((403, {}), (200, {}), (200, [None]), pub.StageBlocked({'reason_code': 'NETWORK'})):
            with self.subTest(response=response), patch.object(pub, 'gitee_api', side_effect=[response]) as api:
                result = pub.ensure_publication_topic('owner', 'repo', FAKE_TOKEN)
            self.assertEqual(result['status'], 'FAILED')
            self.assertFalse(result['write_attempted'])
            self.assertEqual(api.call_count, 1)

    def test_timeout_is_verified_without_second_post(self):
        with patch.object(pub, 'gitee_api', side_effect=[(200, []), pub.StageBlocked({'reason_code': 'NETWORK'}),
                (200, ['MindPlus-Ext2'])]) as api:
            result = pub.ensure_publication_topic('owner', 'repo', FAKE_TOKEN)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(api.call_count, 3)

    def test_successful_post_does_not_replace_readback_verification(self):
        for after in ([], ['MindPlus-Ext2'], {}):
            with self.subTest(after=after), patch.object(pub, 'gitee_api', side_effect=[
                    (200, ['Arduino']), (201, ['MindPlus-Ext2']), (200, after)]):
                self.assertEqual(pub.ensure_publication_topic('owner', 'repo', FAKE_TOKEN)['status'], 'FAILED')

    def test_pending_topic_preserves_push_and_retry_completes_without_repush(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ctx = {'project': base, 'token': FAKE_TOKEN, 'state_dir': base,
                   'project_sha256': 'hash', 'preflight_path': base / 'preflight.json'}
            for topic, expected_code in (({'status': 'FAILED'}, 2), ({'status': 'ALREADY_PRESENT'}, 0)):
                records = [{}, {'branch': 'main', 'commit_sha': 'sha'}, {'remote_name': 'origin',
                    'owner_or_org': 'owner', 'repo_name': 'repo', 'clone_url': 'https://gitee.com/owner/repo.git'}]
                with patch.object(pub, 'context', return_value=ctx), patch.object(pub, 'load_stage', side_effect=records), \
                     patch.object(pub, 'read_json', return_value={}), patch.object(pub, 'drift_check'), \
                     patch.object(pub, 'auth_environment', return_value={}), patch.object(pub, 'git') as git, \
                     patch.object(pub, 'compute_project_hash', return_value=('hash', 1)), \
                     patch.object(pub, 'gitee_api', return_value=(200, {'commit': {'sha': 'sha'}})), \
                     patch.object(pub, 'ensure_publication_topic', return_value=topic), \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    git.return_value.stdout = 'sha'
                    self.assertEqual(pub.cmd_push(argparse.Namespace()), expected_code)
                self.assertFalse(any(call.args[1] == 'push' for call in git.call_args_list))
                saved = json.loads((base / 'publish-push.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['verified_remote_sha'], 'sha')
                if expected_code:
                    self.assertEqual(saved['outcome'], 'PUSHED_TOPIC_PENDING')
                    self.assertIsNone(json.loads(output.getvalue())['next_command'])
                else:
                    self.assertIn('repository_topic_verified', json.loads(output.getvalue())['next_command'])
