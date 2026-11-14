"""Regression tests for CI false-green prevention; run with the backend venv."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ci_results import evaluate, main as report_main


spec = importlib.util.spec_from_file_location(
    'run_ci_postgres', Path(__file__).resolve().parents[2]/'backend/tools/run_ci_postgres.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ResultsTests(unittest.TestCase):
    def evaluate_cases(self, cases, require=True):
        root = ET.Element('testsuites')
        suite = ET.SubElement(root, 'testsuite')
        for name, database, outcome, message in cases:
            case = ET.SubElement(suite, 'testcase', classname='tests.test_postgres', name=name)
            if name.startswith('test_saved_open_and_generate_timings['):
                case.set('classname', 'tests.test_design_baseline_performance')
            if database:
                properties = ET.SubElement(case, 'properties')
                ET.SubElement(properties, 'property', name='panelflow_postgres', value='true')
            if outcome:
                ET.SubElement(case, outcome, message=message)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'results.xml'
            ET.ElementTree(root).write(path)
            return evaluate(path, require)

    def test_database_passes_with_executed_fixture_cases(self):
        text, passed = self.evaluate_cases([('test_db', True, None, '')])
        self.assertTrue(passed)
        self.assertIn('1 PostgreSQL cases', text)

    def test_database_lane_rejects_gate_skip(self):
        text, passed = self.evaluate_cases([
            ('test_db', True, 'skipped', 'Set PANEL_RUN_POSTGRES_TESTS=1'),
            ('test_unit', False, None, ''),
        ])
        self.assertFalse(passed)
        self.assertIn('Required PostgreSQL coverage skipped', text)
        self.assertIn('Set PANEL_RUN_POSTGRES_TESTS=1', text)

    def test_database_lane_rejects_partial_skip_and_missing_coverage(self):
        for cases in (
            [('test_db', True, None, ''), ('test_other_db', True, 'skipped', 'Unexpected skip')],
            [('test_unit', False, None, '')],
            [],
        ):
            with self.subTest(cases=cases):
                self.assertFalse(self.evaluate_cases(cases)[1])

    def test_only_explicit_optional_timings_may_skip(self):
        timing = ('test_saved_open_and_generate_timings[db-12]', True, 'skipped',
                  'Set PANEL_MEASURE_BASELINE=1 for opt-in timing evidence.')
        self.assertTrue(self.evaluate_cases([('test_db', True, None, ''), timing])[1])
        self.assertFalse(self.evaluate_cases([timing])[1])
        wrong_reason = (*timing[:3], 'Database unavailable')
        self.assertFalse(self.evaluate_cases([('test_db', True, None, ''), wrong_reason])[1])

    def test_unit_and_vitest_reports_publish_skips(self):
        text, passed = self.evaluate_cases([('test_unit', False, 'skipped', 'Reason')], require=False)
        self.assertTrue(passed)
        self.assertIn('1 skipped', text)
        self.assertIn('Reason', text)

    def test_failure_and_setup_errors_fail(self):
        for outcome in ('failure', 'error'):
            self.assertFalse(self.evaluate_cases([('test_db', True, outcome, 'Failed')])[1])

    def test_missing_and_malformed_report_fail_and_write_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)/'results.xml'
            summary = Path(directory)/'summary.md'
            for contents in (None, '<not-xml'):
                if contents:
                    report.write_text(contents)
                with patch.object(sys, 'argv', ['ci_results.py', str(report), '--label', 'Guard']), \
                        patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}, clear=True):
                    self.assertEqual(report_main(), 1)
            self.assertIn('Missing, unreadable or invalid JUnit report', summary.read_text())


class PostgresRunnerTests(unittest.TestCase):
    def run_profile(self, snapshots, child_status=0):
        with patch.dict(os.environ, {
            'PANEL_RUN_POSTGRES_TESTS': '1', 'PGHOST': '127.0.0.1', 'PGPORT': '15432',
            'PGUSER': 'panel_ci', 'DATABASE_URL': 'must-not-be-used',
            'PANEL_DATABASE_URL': 'must-not-be-used',
        }, clear=True), patch.object(sys, 'argv', ['run_ci_postgres.py', '--junitxml=report.xml']), \
                patch.object(runner, 'snapshot', side_effect=snapshots), \
                patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], child_status)) as child:
            status = runner.main()
            return status, child

    def test_child_uses_backend_interpreter_and_job_service(self):
        status, child = self.run_profile([{'postgres'}, {'postgres'}])
        self.assertEqual(status, 0)
        command = child.call_args.args[0]
        self.assertEqual(command[:3], [sys.executable, '-m', 'pytest'])
        environment = child.call_args.kwargs['env']
        self.assertEqual(environment['PANEL_RUN_POSTGRES_TESTS'], '1')
        self.assertNotIn('PANEL_DATABASE_URL', environment)
        self.assertEqual(environment['DATABASE_URL'],
                         'postgresql+psycopg://panel_ci@127.0.0.1:15432/panelflow_ci_config_only')

    def test_failed_tests_still_audit_cleanup_and_keep_exit_status(self):
        status, _ = self.run_profile([{'postgres'}, {'postgres'}], child_status=2)
        self.assertEqual(status, 2)

    def test_leaked_or_deleted_database_fails_a_passing_suite(self):
        for before, after in (
            ({'postgres'}, {'postgres', 'panel_integration_test_'+'a'*32}),
            ({'postgres', 'untouched'}, {'postgres'}),
        ):
            self.assertEqual(self.run_profile([before, after])[0], 1)

    def test_preexisting_disposable_database_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.run_profile([{'postgres', 'panel_policy_upgrade_'+'a'*32}])

    def test_database_profile_requires_explicit_enablement(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(sys, 'argv', ['run_ci_postgres.py', '--junitxml=report.xml']), \
                self.assertRaises(SystemExit) as error:
            runner.main()
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
