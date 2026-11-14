"""Review retained coupon evidence without executing or importing a native kernel.

Exit 1 means reference qualification failed, even if STEP export/reopen succeeded.
Writes a new review.json only; raw native evidence is never overwritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

from tests.fixtures.cad_reference.spike import HERE, inspect_reference


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def review(evidence, runtime):
    reference, _, _, script, _ = inspect_reference()
    expected = reference['independent_expectations']
    tolerance = expected['tolerances']['bounds_mm']
    exported = json.loads((evidence / 'export.json').read_text())
    reopened = json.loads((evidence / 'reopen.json').read_text())
    processes = {mode: json.loads((evidence / (mode + '.process.json')).read_text())
                 for mode in ('export', 'reopen')}
    mapping = json.loads((evidence / 'mapping.json').read_text())
    checks = []

    def check(name, passed, **details):
        checks.append({'name': name, 'result': 'PASS' if passed else 'FAIL', **details})

    def bounds(name, actual, target):
        delta = max(abs(a-b) for a, b in zip(actual, target))
        check(name, len(actual) == len(target) and math.isfinite(delta) and delta <= tolerance,
              actual_mm=actual, expected_mm=target, max_error_mm=delta, tolerance_mm=tolerance)

    step = evidence / 'panel_model.step'
    check('retained_step_hash', digest(step) == exported['step_sha256'] == reopened['step_sha256'])
    check('actual_repository_script', (evidence / 'existing-export.py').read_text() == script)
    check('unchanged_reference', digest(evidence / 'reference.json') == digest(HERE / 'reference.json'))
    check('fresh_process', exported['pid'] != reopened['pid'] and
          processes['export']['pid'] != processes['reopen']['pid'])
    for mode, report in (('export', exported), ('reopen', reopened)):
        check(mode + '_process', processes[mode]['exit_code'] == 0)
        check(mode + '_versions', report['freecad_version'] == '1.0.2' and report['python_major_minor'] == [3, 11])
        check(mode + '_units_mm', report['step_units_mm'])
        check(mode + '_count', report['solid_count'] == expected['rendered_solid_count'], actual=report['solid_count'])
        check(mode + '_valid', report['valid'] and all(s['valid'] for s in report['solids']))
        bounds(mode + '_assembly_bounds', report['bounds_mm'], expected['assembly_bounds_mm'])
    before = sorted(exported['solids'], key=lambda s: s['bounds_mm'])
    after = sorted(reopened['solids'], key=lambda s: s['bounds_mm'])
    bound_errors = [max(abs(a-b) for a, b in zip(s['bounds_mm'], t['bounds_mm'])) for s, t in zip(before, after)]
    volume_errors = [abs(s['volume_mm3']-t['volume_mm3']) for s, t in zip(before, after)]
    volume_limits = [max(1e-6, abs(s['volume_mm3'])*expected['tolerances']['roundtrip_volume_relative']) for s in before]
    check('all_solid_roundtrips', len(before) == len(after) == 42 and
          all(e <= tolerance for e in bound_errors) and
          all(e <= limit for e, limit in zip(volume_errors, volume_limits)),
          max_bounds_error_mm=max(bound_errors), max_volume_error_mm3=max(volume_errors),
          max_volume_relative_error=max(e/abs(s['volume_mm3']) for e, s in zip(volume_errors, before)))
    for item in mapping:
        key = {'CAD-BACKPLATE': 'backplate_bounds_mm', 'PDM-COUPON-BODY': 'mounted_part_bounds_mm',
               'CAD-ROUTE-CONN-REFERENCE': 'wire_bounds_mm'}.get(item['source']['id'])
        if key:
            source = exported['objects'][item['freecad_name']]
            bounds('export_' + key, source['bounds_mm'], expected[key])
            # Geometry matching identifies the round-tripped solid only for this
            # diagnostic. It does not prove source/occurrence identity in STEP.
            candidates = sorted(reopened['solids'], key=lambda s:
                                max(abs(a-b) for a, b in zip(s['bounds_mm'], source['bounds_mm'])))
            bounds('reopen_' + key, candidates[0]['bounds_mm'], expected[key])
    archive = runtime / reference['native_target']['asset']
    checksum = runtime / (archive.name + '-SHA256.txt')
    archive_digest = digest(archive)
    check('official_archive_checksum', archive_digest == reference['native_target']['sha256'] == checksum.read_text().split()[0])
    extracted = runtime / 'squashfs-root'
    package_text = (extracted / 'packages.txt').read_text()
    names = {'freecad', 'python', 'occt', 'qt-main', 'pyside2', 'libstdcxx', 'libgcc', 'ffmpeg'}
    package_lines = [line.strip() for line in package_text.splitlines() if line.split() and line.split()[0] in names]
    selected = [extracted / p for p in ('AppRun', 'usr/bin/freecadcmd', 'usr/bin/python', 'packages.txt')]
    selected += [Path(p) for p in exported['loaded_native_libraries']]
    licenses = [p for p in (extracted / 'usr').rglob('*') if p.is_file() and
                any(word in p.name.lower() for word in ('license', 'licence', 'copying', 'copyright'))]
    result = {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'native_cad': 'FAIL' if any(c['result'] == 'FAIL' for c in checks) else 'PASS_NUMERICAL_CHECKS_ONLY',
        'tolerance_authority': 'Human approved unchanged reference-test numbers in attempt-02 conversation; no manufacturing/distribution approval',
        'checks': checks,
        'runtime': {'directory': str(runtime), 'archive_bytes': archive.stat().st_size,
                    'archive_sha256': archive_digest, 'official_checksum_text': checksum.read_text(),
                    'package_lines': package_lines, 'selected_file_sha256': {str(p.relative_to(extracted)): digest(p) for p in selected},
                    'extracted_regular_file_bytes': sum(p.stat().st_size for p in extracted.rglob('*') if p.is_file() and not p.is_symlink()),
                    'license_notice_file_sha256': {str(p.relative_to(extracted)): digest(p) for p in licenses}},
        'host': {'platform': platform.platform(), 'machine': platform.machine(),
                 'controller_executable': sys.executable, 'controller_prefix': sys.prefix,
                 'controller_python': sys.version, 'os_release': Path('/etc/os-release').read_text()},
        'raw_file_sha256': {p.name: digest(p) for p in evidence.iterdir() if p.is_file()},
        'limitations': ['Same OCCT fresh-process reopen, not another kernel',
                        'Geometric matching does not prove named STEP assembly identity',
                        'One diagnostic sample; no performance target or production isolation qualification',
                        'Distribution and full dependency license review remain human responsibilities'],
    }
    with (evidence / 'review.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--runtime-dir', required=True, type=Path)
    args = parser.parse_args()
    result = review(args.evidence_dir.resolve(), args.runtime_dir.resolve())
    print(json.dumps({'native_cad': result['native_cad'], 'checks': result['checks'],
                      'review': str(args.evidence_dir / 'review.json')}, indent=2))
    sys.exit(1 if result['native_cad'] == 'FAIL' else 0)


if __name__ == '__main__':
    main()
