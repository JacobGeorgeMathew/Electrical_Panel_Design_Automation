"""Explicit fixture adapters and observed-output capture; never used by HTTP runtime.

Run from backend: .venv/bin/python -m tests.design_baseline_support capture
The capture prints a proposed apply_patch payload; it never rewrites expectations.
"""
import hashlib
import importlib.metadata
import json
import platform
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer, LayoutResult
from app.algorithms.duct_routing import DuctRouter
from app.algorithms.layout_config import LayoutConfig
from app.models.cem import ComponentRef, ConnectionRef, NetRef
from app.models.pdm import CableDuct, PhysicalComponent, PhysicalDesignModel, Position3D
from app.persistence.assets import canonical_json, content_hash, primitive_glb
from app.persistence.repositories import MemoryComponents, MemoryEnclosures, MemoryProjects
from app.repositories.component_repository import ComponentRepository
from app.repositories.enclosure_repository import EnclosureRepository
from app.services.cad_engine import CADEngine
from app.services.orchestrator import DesignOrchestrator
from app.services.project_service import ENGINE_VERSION
from app.services.requirement_engine import RequirementEngine

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / 'fixtures/design_baselines'
CASES = json.loads((FIXTURES / 'cases.json').read_text())


def engine(case, fixed_enclosure=None):
    """Inject all fixture inputs; no project-file reads/writes or database fallback."""
    values = {**CASES['requirements'], 'num_feeders': case['num_feeders']}
    project = dict(id=case['project_id'], name=case['id'], archetype='DB', requirements=values)
    templates = json.loads((BACKEND / 'app/data/panel_templates.json').read_text())
    hardware = json.loads((BACKEND / 'app/data/panel_hardware.json').read_text())['items']
    return DesignOrchestrator(
        project_repo=MemoryProjects(project),
        comp_repo=MemoryComponents(ComponentRepository().get_all()),
        enclosure_repo=MemoryEnclosures(EnclosureRepository().get_all(), fixed_enclosure),
        req_engine=RequirementEngine(templates={t['archetype']: t for t in templates}),
        hardware_catalog=hardware,
    )


def generate(case):
    return engine(case).generate_design(case['project_id'], persist_requirements=False)


def pins():
    paths = [BACKEND / 'requirements.txt', FIXTURES / 'cases.json']
    paths += sorted((BACKEND / 'app/data').glob('*.json'))
    # Hash the actual contracts and implementation, not just a manually bumped label.
    for folder in ('models', 'services', 'algorithms', 'repositories'):
        paths += sorted((BACKEND / 'app' / folder).glob('*.py'))
    paths += [BACKEND / 'app/persistence/assets.py', BACKEND / 'app/persistence/repositories.py']
    return {
        'engine_version': ENGINE_VERSION,
        'glb_generator': 'panelstudio-primitives/3',
        'python': platform.python_version(),
        'packages': {p: importlib.metadata.version(p) for p in ('ortools', 'shapely', 'pydantic', 'numpy')},
        'layout': json.loads(json.dumps(asdict(LayoutConfig()), default=lambda x: sorted(x))),
        'input_and_source_sha256': {
            str(p.relative_to(BACKEND)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    }


def artifacts(package):
    """Match ProjectService.generate_files: GLB version 3, exact UTF-8 script bytes."""
    return {
        'preview.glb': primitive_glb(package['cad']['primitives'], generator_version='3'),
        'assembly.py': CADEngine().export_freecad_script(PhysicalDesignModel(**package['pdm'])).encode('utf-8'),
    }


def observation(package):
    cem, pdm = package['cem'], package['pdm']
    return {
        'normalization': [],  # CEM/PDM/direct-engine outputs currently contain no timestamps.
        'hashes': {**{k: {'sha256': content_hash(v), 'bytes': len(canonical_json(v))} for k, v in package.items()},
                   'package': {'sha256': content_hash(package), 'bytes': len(canonical_json(package))},
                   **{k: {'sha256': hashlib.sha256(v).hexdigest(), 'bytes': len(v)} for k, v in artifacts(package).items()}},
        'state': cem['state'],
        'enclosure': [pdm[k] for k in ('enclosure_id', 'enclosure_width', 'enclosure_height', 'enclosure_depth')],
        'category_counts': dict(Counter(c['category'] for c in cem['components'])),
        'net_ids': [n['id'] for n in cem['nets']],
        'components': [[c['id'], c['catalog_id'], [t['id'] for t in c['terminals']]] for c in cem['components']],
        'connections': [[c[k] for k in ('id', 'net_id', 'from_component', 'from_terminal', 'to_component', 'to_terminal')]
                        for c in cem['connections']],
        'routes': [[r[k] for k in ('id', 'conductor_id', 'net_id', 'from_component', 'from_terminal', 'to_component', 'to_terminal')]
                   + [r['duct_ids']] for r in pdm['routes']],
        'counts': {k: len(pdm[k]) for k in ('components', 'routes', 'ducts', 'rails', 'accessories')},
        'physical_violations': pdm['validation_results'],
    }


def placement_failure(case):
    w, h, d = case['component_mm']
    component = ComponentRef(id='WIDE', catalog_id='SYNTHETIC', name='Too wide', category='MCB',
        current_rating=0, breaking_capacity=0, poles=1, width=w, height=h, depth=d,
        mounting='DIN', heat_loss=0, cad_model='')
    return CPSATPlacementOptimizer().solve([component], *case['enclosure_mm'])


def routing_inputs(case):
    parts = [PhysicalComponent(id='PDM-'+key, cem_component_id=key, name=key, category='TERMINAL',
        position=Position3D(x=x, y=y, z=20), width=20, height=20, depth=20,
        zone_name='TERMINAL', heat_loss_watts=0, cad_model='',
        terminals=[dict(id='T', x=tx, y=10, z=10)]) for key, x, y, tx in case['components']]
    if case['wall']:
        wall = case['wall']
        parts.append(PhysicalComponent(id='PDM-WALL', cem_component_id='WALL', name='Wall',
            category='OBSTACLE', position=Position3D(x=wall['x'], y=wall['y'], z=0),
            width=wall['width'], height=wall['height'], depth=120,
            zone_name='TEST', heat_loss_watts=0, cad_model=''))
    ducts = [CableDuct(id=key, label=key, x=x, y=y, z=10, width=w, height=h, depth=60,
        orientation='VERTICAL' if h > w else 'HORIZONTAL') for key, x, y, w, h in case['ducts']]
    connection = ConnectionRef(**case['connection'])
    net = NetRef(id=connection.net_id, name='Test', voltage_level=230, wire_class='POWER', connections=[connection])
    return LayoutResult(True, 'FEASIBLE', components=parts), [net], ducts


def route_failure(case):
    layout, nets, ducts = routing_inputs(case)
    return DuctRouter().route_layout(layout, nets, *case['enclosure_mm'], ducts=ducts)


def fixture_text(value):
    # One reference record per line keeps identities reviewable without huge files.
    lines = ['{']
    for index, (key, item) in enumerate(value.items()):
        suffix = ',' if index < len(value)-1 else ''
        if isinstance(item, list) and item:
            lines.append('  '+json.dumps(key)+': [')
            lines.extend('    '+json.dumps(row, ensure_ascii=False)+(',' if i < len(item)-1 else '')
                         for i, row in enumerate(item))
            lines.append('  ]'+suffix)
        else:
            lines.append('  '+json.dumps(key)+': '+json.dumps(item, ensure_ascii=False)+suffix)
    return '\n'.join(lines+['}', ''])


if __name__ == '__main__':
    if sys.argv[1:] == ['capture']:
        outputs = {'pins.json': json.dumps(pins(), indent=2)+'\n'}
        outputs.update({case['id']+'.observed.json': fixture_text(observation(generate(case))) for case in CASES['feasible']})
        print('*** Begin Patch')
        for name, body in outputs.items():
            print('*** Add File: backend/tests/fixtures/design_baselines/'+name)
            print('\n'.join('+'+line for line in body.splitlines()))
        print('*** End Patch')
    elif len(sys.argv) == 3 and sys.argv[1] == 'package':
        print(json.dumps(generate(next(c for c in CASES['feasible'] if c['id'] == sys.argv[2]))))
    else:
        raise SystemExit('Use capture or package db-12|db-16')
