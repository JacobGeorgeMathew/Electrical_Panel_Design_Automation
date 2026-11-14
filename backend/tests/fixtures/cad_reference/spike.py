"""Bounded, opt-in CAD experiment; no application/DB worker is installed.

From backend: .venv/bin/python -m tests.fixtures.cad_reference.spike inspect
Native: same module, native --freecad-command /absolute/path/to/freecadcmd
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import struct
import subprocess
import sys
import time

from app.models.pdm import PhysicalDesignModel
from app.persistence.assets import primitive_glb
from app.services.cad_engine import CADEngine
from app.services.wire_geometry import build_wire_geometry

HERE = Path(__file__).resolve().parent


def load_reference():
    reference = json.loads((HERE / 'reference.json').read_text())
    pdm = PhysicalDesignModel(**reference['pdm'])
    for route in pdm.routes:
        route.geometry = build_wire_geometry(route, pdm)
    return reference, pdm


def close(actual, expected, tolerance=1e-7):
    if len(actual) != len(expected) or any(not math.isfinite(a) or not math.isfinite(b) or abs(a-b) > tolerance
                                           for a, b in zip(actual, expected)):
        raise AssertionError((actual, expected, tolerance))


def box_bounds(primitive):
    # Independent corner transform, rather than trusting the export's placement.
    dims = [primitive['dimensions'][k] for k in ('width', 'height', 'depth')]
    qx, qy, qz, qw = primitive.get('rotation_xyzw', [0, 0, 0, 1])
    if abs(qx) + abs(qy) > 1e-9:
        raise AssertionError('Coupon expects rotation about z only')
    angle = 2 * math.atan2(qz, qw)
    co, si = math.cos(angle), math.sin(angle)
    pos = primitive['position']
    corners = [(pos['x']+co*x-si*y, pos['y']+si*x+co*y, pos['z']+z)
               for x in (-dims[0]/2, dims[0]/2) for y in (-dims[1]/2, dims[1]/2)
               for z in (-dims[2]/2, dims[2]/2)]
    return [min(p[k] for p in corners) for k in range(3)] + [max(p[k] for p in corners) for k in range(3)]


def inspect_reference():
    started = time.perf_counter()
    reference, pdm = load_reference()
    expected = reference['independent_expectations']
    cad = CADEngine().generate_parametric_geometry(pdm)
    primitives = [p for p in cad['primitives'] if p['type'] in {'BOX', 'CYLINDER', 'TUBE'}]
    counts = Counter(p['type'] for p in primitives)
    assert counts == {'BOX': expected['box_count'], 'TUBE': expected['tube_count']}
    assert len(primitives) == expected['rendered_solid_count']
    assert len({p['id'] for p in primitives}) == len(primitives)
    by_id = {p['id']: p for p in primitives}
    close(box_bounds(by_id['PDM-COUPON-BODY']), expected['mounted_part_bounds_mm'])
    close(box_bounds(by_id['CAD-BACKPLATE']), expected['backplate_bounds_mm'])
    boxes = [box_bounds(p) for p in primitives if p['type'] == 'BOX']
    close([min(b[k] for b in boxes) for k in range(3)] +
          [max(b[k+3] for b in boxes) for k in range(3)], expected['assembly_bounds_mm'])
    route = pdm.routes[0]
    geometry = route.geometry
    close(list(geometry.centerline[0].model_dump().values()), expected['wire_terminal_endpoints_mm'][0])
    close(list(geometry.centerline[-1].model_dump().values()), expected['wire_terminal_endpoints_mm'][1])
    close(geometry.bend_radii_mm, [expected['wire_bend_radius_mm']])
    close([geometry.centerline_length_mm], [expected['ideal_circular_centerline_length_mm']],
          expected['tolerances']['sampled_length_mm'])
    # Preserve unresolved electrical evidence; native validity cannot resolve it.
    assert route.status == 'UNRESOLVED'
    assert any(c['status'] == 'UNRESOLVED' for c in geometry.checks)
    wire = by_id['CAD-ROUTE-CONN-REFERENCE']
    assert (wire['route_id'], wire['net_id'], wire['conductor_id']) == (route.id, route.net_id, route.conductor_id)
    script = CADEngine().export_freecad_script(pdm)
    compile(script, 'existing-export.py', 'exec')
    glb = primitive_glb(cad['primitives'], generator_version='3')
    json_length = struct.unpack_from('<I', glb, 12)[0]
    document = json.loads(glb[20:20+json_length])
    assert len(document['nodes']) == len(primitives)
    nodes = {n['extras']['id']: n for n in document['nodes']}
    close(nodes['PDM-COUPON-BODY']['translation'], [0.09, 0.12, 0.03])
    assert nodes['PDM-COUPON-BODY']['extras']['cem_component_id'] == 'COUPON'
    assert nodes[wire['id']]['extras']['route_id'] == route.id
    # Current GLB loses conductor_id even though the CAD descriptor retains it.
    assert 'conductor_id' not in nodes[wire['id']]['extras']
    peak_rss = None
    if sys.platform == 'linux':
        import resource
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return reference, pdm, primitives, script, {
        'status': 'PASS_NON_NATIVE_COUPON_CHECKS', 'counts': dict(counts),
        'script_sha256': hashlib.sha256(script.encode()).hexdigest(),
        'script_bytes': len(script.encode()), 'glb_sha256': hashlib.sha256(glb).hexdigest(),
        'glb_bytes': len(glb), 'sampled_wire_length_mm': geometry.centerline_length_mm,
        'elapsed_ms': (time.perf_counter()-started)*1000,
        'process_max_rss_kib_linux': peak_rss,
        'native_cad': 'NOT_RUN', 'engineering_approval': 'UNRESOLVED',
    }


def environment():
    return {'executable': sys.executable, 'prefix': sys.prefix, 'python': sys.version,
            'platform': platform.platform(), 'machine': platform.machine(),
            'modules': {n: importlib.util.find_spec(n) is not None for n in ('FreeCAD', 'Part', 'OCP', 'OCC', 'cadquery')},
            'executables': {n: shutil.which(n) for n in ('FreeCADCmd', 'freecadcmd', 'FreeCAD', 'freecad', 'conda', 'micromamba', 'docker')}}


def run_child(command, mode, scratch, launcher_args=()):
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'DISPLAY', 'WAYLAND_DISPLAY'):
        env.pop(key, None)
    env.update(PANEL_CAD_SPIKE_MODE=mode, PANEL_CAD_SPIKE_DIR=str(scratch), QT_QPA_PLATFORM='offscreen')
    # A scratch profile avoids modifying the user's ordinary FreeCAD preferences.
    args = [command, *launcher_args, '--user-cfg', str(scratch / 'user.cfg'), '--system-cfg', str(scratch / 'system.cfg'),
            str(HERE / 'native_worker.py')]
    started = time.perf_counter()
    process = subprocess.Popen(args, cwd=scratch, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        (scratch / (mode + '.stdout.log')).write_bytes(stdout)
        (scratch / (mode + '.stderr.log')).write_bytes(stderr)
        raise RuntimeError(mode + ' exceeded 60 seconds') from None
    (scratch / (mode + '.stdout.log')).write_bytes(stdout)
    (scratch / (mode + '.stderr.log')).write_bytes(stderr)
    process_report = {'args': args, 'cwd': str(scratch), 'pid': process.pid,
                      'process_wall_ms': (time.perf_counter()-started)*1000,
                      'exit_code': process.returncode}
    (scratch / (mode + '.process.json')).write_text(json.dumps(process_report, indent=2) + '\n')
    if process.returncode:
        raise RuntimeError(f'{mode}: exit {process.returncode}; stdout={stdout[-2000:]!r}; stderr={stderr[-2000:]!r}')
    report = json.loads((scratch / (mode + '.json')).read_text())
    report.update(process_report)
    return report


def native(command, evidence_dir, launcher_args=()):
    if sys.platform != 'linux' or not Path(command).is_absolute() or not os.access(command, os.X_OK):
        raise ValueError('Supply an executable absolute path to the qualified Linux FreeCADCmd')
    reference, pdm, primitives, script, inspected = inspect_reference()
    scratch = Path(evidence_dir).resolve()
    # Never overwrite a prior experiment, including a failed one.
    scratch.mkdir(parents=True, exist_ok=False)
    try:
        (scratch / 'existing-export.py').write_text(script)
        # Sidecar maps existing sequential FreeCAD names to source IDs; STEP names
        # are not assumed to preserve identity. No production adapter is created.
        all_primitives = CADEngine().generate_parametric_geometry(pdm)['primitives']
        mapping = [{'freecad_name': 'PanelPart_'+str(i), 'source': p} for i, p in enumerate(all_primitives)
                   if p['type'] in {'BOX', 'CYLINDER', 'TUBE'}]
        (scratch / 'mapping.json').write_text(json.dumps(mapping, indent=2) + '\n')
        (scratch / 'reference.json').write_bytes((HERE / 'reference.json').read_bytes())
        exported = run_child(command, 'export', scratch, launcher_args)
        reopened = run_child(command, 'reopen', scratch, launcher_args)
        expected = reference['independent_expectations']
        tolerance = expected['tolerances']['bounds_mm']
        for report in (exported, reopened):
            assert report['freecad_version'] == '1.0.2' and report['python_major_minor'] == [3, 11]
            assert report['valid'] and report['solid_count'] == expected['rendered_solid_count']
            close(report['bounds_mm'], expected['assembly_bounds_mm'], tolerance)
        assert reopened['step_units_mm']
        assert exported['step_sha256'] == reopened['step_sha256']
        assert len(exported['solids']) == len(reopened['solids'])
        for before, after in zip(sorted(exported['solids'], key=lambda s: s['bounds_mm']),
                                 sorted(reopened['solids'], key=lambda s: s['bounds_mm'])):
            assert before['valid'] and after['valid']
            close(before['bounds_mm'], after['bounds_mm'], tolerance)
            assert abs(before['volume_mm3']-after['volume_mm3']) <= max(1e-6, abs(before['volume_mm3'])*expected['tolerances']['roundtrip_volume_relative'])
        by_name = exported['objects']
        for item in mapping:
            if item['source']['id'] in {'PDM-COUPON-BODY', 'CAD-ROUTE-CONN-REFERENCE'}:
                key = 'mounted_part_bounds_mm' if item['source']['type'] == 'BOX' else 'wire_bounds_mm'
                close(by_name[item['freecad_name']]['bounds_mm'], expected[key], tolerance)
        result = {'status': 'EXPERIMENT_REOPENED_PENDING_REVIEW',
                'export': exported, 'reopen': reopened, 'sidecar': mapping,
                'non_native_checks': inspected, 'artifact_retention': str(scratch),
                'tolerances_checked': expected['tolerances'],
                'native_profile_acceptance': 'Requires runtime provenance and human tolerance review; no automatic approval'}
        (scratch / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    except Exception as error:
        (scratch / 'failure.json').write_text(json.dumps({'error': str(error), 'type': type(error).__name__}, indent=2) + '\n')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect', 'native'))
    parser.add_argument('--freecad-command')
    parser.add_argument('--launcher-arg', action='append', default=[], help='Argument before FreeCAD options (e.g. AppRun freecadcmd)')
    parser.add_argument('--evidence-dir', help='New persistent directory; must not already exist')
    args = parser.parse_args()
    if args.mode == 'inspect':
        print(json.dumps({'environment': environment(), 'inspection': inspect_reference()[-1]}, indent=2))
    else:
        if not args.freecad_command or not args.evidence_dir:
            parser.error('native requires --freecad-command and --evidence-dir')
        print(json.dumps(native(args.freecad_command, args.evidence_dir, args.launcher_arg), indent=2))


if __name__ == '__main__':
    main()
