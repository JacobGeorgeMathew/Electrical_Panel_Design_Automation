"""Publish pytest/Vitest JUnit summaries and reject missing database coverage."""
import argparse
import html
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def optional_timing_skip(case):
    """Only the existing explicitly opt-in timing profile may skip in the DB lane."""
    skipped = case.find('skipped')
    return (
        case.get('classname') == 'tests.test_design_baseline_performance'
        and case.get('name', '').startswith('test_saved_open_and_generate_timings[')
        and skipped is not None
        and skipped.get('message') == 'Set PANEL_MEASURE_BASELINE=1 for opt-in timing evidence.'
    )


def evaluate(path, require_postgres=False):
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    skipped = [case for case in cases if case.find('skipped') is not None]
    failed = [case for case in cases if case.find('failure') is not None or case.find('error') is not None]
    database = [case for case in cases if any(
        prop.get('name') == 'panelflow_postgres' and prop.get('value') == 'true'
        for prop in case.findall('./properties/property')
    )]
    errors = []
    if not cases:
        errors.append('No test cases were reported.')
    if failed or any(int(suite.get('errors', '0')) or int(suite.get('failures', '0'))
                     for suite in root.iter('testsuite')):
        errors.append('The test report contains failures or errors.')
    if require_postgres:
        required = [case for case in database if not optional_timing_skip(case)]
        if not required:
            errors.append('No required PostgreSQL test cases were reported.')
        if any(case.find('skipped') is not None for case in required):
            errors.append('Required PostgreSQL coverage skipped; this lane must execute it.')
    lines = [f'{len(cases)} tests; {len(failed)} failed/errored; {len(skipped)} skipped; '
             f'{len(database)} PostgreSQL cases.']
    for case in skipped:
        reason = case.find('skipped').get('message') or case.find('skipped').text or 'No reason supplied'
        lines.append('SKIP '+case.get('classname', '')+'.'+case.get('name', '')+': '+reason)
    lines.extend('FAIL: '+error for error in errors)
    return '\n'.join(lines), not errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--label', required=True)
    parser.add_argument('--require-postgres', action='store_true')
    args = parser.parse_args()
    try:
        text, passed = evaluate(args.report, args.require_postgres)
    except (OSError, ET.ParseError, ValueError):
        text, passed = 'FAIL: Missing, unreadable or invalid JUnit report.', False
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write('### '+html.escape(args.label)+'\n\n<pre>'+html.escape(text)+'</pre>\n\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
