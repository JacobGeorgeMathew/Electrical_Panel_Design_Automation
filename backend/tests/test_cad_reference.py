"""Non-native checks for the bounded P0-T05 coupon; no kernel pass is implied."""
import math
import json
import sys

import pytest

from app.services.cad_engine import CADEngine
from app.services.design_errors import DesignError
from tests.fixtures.cad_reference.spike import inspect_reference, load_reference, native, run_child


def test_cad_coupon_independent_bounds_offsets_units_and_identities():
    reference, pdm, primitives, script, result = inspect_reference()
    assert result['native_cad'] == 'NOT_RUN'
    assert len(primitives) == reference['independent_expectations']['rendered_solid_count']
    # Sampled fillet must remain distinguishable from an analytic circular arc.
    ideal = reference['independent_expectations']['ideal_circular_centerline_length_mm']
    assert 0 < ideal-pdm.routes[0].geometry.centerline_length_mm < 0.02


def test_cad_coupon_trunk_and_terminal_mapping_are_independent_of_export():
    reference, pdm = load_reference()
    component, route, duct = pdm.components[0], pdm.routes[0], pdm.ducts[0]
    terminal = component.terminals[0]
    angle = math.radians(component.rotation_deg)
    x, y = terminal['x']-component.width/2, terminal['y']-component.height/2
    endpoint = (component.position.x+component.width/2+x*math.cos(angle)-y*math.sin(angle),
                component.position.y+component.height/2+x*math.sin(angle)+y*math.cos(angle),
                component.position.z+terminal['z'])
    assert endpoint == pytest.approx(reference['independent_expectations']['wire_terminal_endpoints_mm'][0])
    geometry = route.geometry
    radius = route.wire_diameter_mm/2
    trunk = geometry.centerline[geometry.duct_entry_index:geometry.duct_exit_index+1]
    assert len(trunk) >= 2
    for p in trunk:
        assert duct.x+duct.wall_mm+radius <= p.x <= duct.x+duct.width-duct.wall_mm-radius
        assert duct.y+duct.wall_mm+radius <= p.y <= duct.y+duct.height-duct.wall_mm-radius
        assert duct.z+duct.wall_mm+radius <= p.z <= duct.z+duct.depth-duct.wall_mm-radius
    assert route.conductor_id == 'CONN-REFERENCE'
    assert geometry.route_id == route.id and geometry.cad_object_id == 'CAD-'+route.id


def test_cad_coupon_cannot_export_a_missing_or_failed_wire_geometry():
    _, pdm = load_reference()
    for replacement in (None, pdm.routes[0].geometry.model_copy(update={'status': 'UNRESOLVED'})):
        pdm.routes[0].geometry = replacement
        with pytest.raises(DesignError) as failure:
            CADEngine().export_freecad_script(pdm)
        assert failure.value.code == 'WIRE_GEOMETRY_UNVALIDATED'


def test_native_evidence_directory_cannot_overwrite_a_prior_run(tmp_path):
    sentinel = tmp_path / 'panel_model.step'
    sentinel.write_bytes(b'prior evidence')
    with pytest.raises(FileExistsError):
        native(sys.executable, tmp_path)
    assert sentinel.read_bytes() == b'prior evidence'


def test_failed_child_retains_logs_and_process_evidence(tmp_path):
    # Python rejects FreeCAD's CLI options: exercise a real failed subprocess.
    with pytest.raises(RuntimeError, match='export: exit'):
        run_child(sys.executable, 'export', tmp_path)
    report = json.loads((tmp_path / 'export.process.json').read_text())
    assert report['exit_code'] != 0
    assert report['cwd'] == str(tmp_path)
    assert report['process_wall_ms'] > 0
    assert (tmp_path / 'export.stdout.log').exists()
    assert (tmp_path / 'export.stderr.log').read_bytes()
