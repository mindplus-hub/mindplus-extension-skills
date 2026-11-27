import json
import tempfile
import unittest
from pathlib import Path

from test_workflow import run_script, basic_handoff, publish_fixture
from validate_handoff import validate
from check_basic_review import BASIC_CHECKS
from test_workflow import basic_report_fixture


class IssueLevelTests(unittest.TestCase):
    def test_p0_cannot_be_hidden_as_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, _ = publish_fixture(Path(directory))
            data = basic_handoff(project)
            data['checks'].append({'id': 'syntax_error', 'priority': 'P0', 'required': False,
                                   'result': 'FAIL', 'evidence': [str(project)]})
            self.assertTrue(any('P0' in error for error in validate(data, None, True)))
            data['checks'][-1]['required'] = True
            self.assertTrue(any('non-passing required' in error for error in validate(data, None, True)))

    def test_advisory_findings_can_advance_to_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project, _, _ = publish_fixture(base)
            start = run_script('mpa.py', 'start', '--goals', 'REVIEW,PUBLISH', '--project-root', str(project),
                               '--work-root', str(base), '--run-id', 'levels', '--auth', 'commit', '--auth', 'push')
            self.assertEqual(start.returncode, 0, start.stdout)
            args = ['mpa.py', 'handoff', '--work-root', str(base), '--run-id', 'levels', '--workflow',
                    'REVIEW_EXISTING', '--status', 'PASS', '--outcome', 'REVIEWED_BASIC']
            args += ["--artifact", "basic_review=" + str(basic_report_fixture(project))]
            for check in sorted(BASIC_CHECKS):
                args += ['--check', check + '=PASS', '--evidence', check + '=' + str(project)]
            for check, priority in (('block_color', 'P1'), ('trailing_spaces', 'P2')):
                args += ['--check', check + '=FAIL', '--priority', check + '=' + priority,
                         '--evidence', check + '=' + str(project)]
            result = run_script(*args)
            self.assertEqual(result.returncode, 0, result.stdout)
            data = json.loads((base / '.mindplus-agent/runs/levels/handoffs/REVIEW_EXISTING.json').read_text())
            advisory = [check for check in data['checks'] if check.get('priority')]
            self.assertEqual(len(advisory), 2)
            self.assertTrue(all(check['required'] is False and check['result'] == 'FAIL' for check in advisory))
            blocked = run_script(*args, '--check', 'syntax=FAIL', '--priority', 'syntax=P0',
                                 '--optional', 'syntax', '--evidence', 'syntax=' + str(project))
            self.assertNotEqual(blocked.returncode, 0)
            downgraded = run_script(*args, '--priority', 'config_schema=P1')
            self.assertNotEqual(downgraded.returncode, 0)
            advanced = run_script('mpa.py', 'transition', '--work-root', str(base), '--run-id', 'levels')
            self.assertEqual(advanced.returncode, 0, advanced.stdout)
            self.assertEqual(json.loads(advanced.stdout)['advanced_to'], 'PUBLISH_GITEE')


if __name__ == '__main__':
    unittest.main()
