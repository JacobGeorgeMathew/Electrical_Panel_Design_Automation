"""Draft physical rerouting from saved CEM connectivity and edited PDM placement."""
from types import SimpleNamespace
from app.algorithms.duct_routing import DuctRouter
from app.algorithms.jps_theta_star import RoutePlanningError
from app.algorithms.layout_config import LayoutConfig
from app.models.pdm import ValidationViolation
from app.services.validation_engine import ValidationEngine
from app.services.wire_geometry import build_wire_geometry


def reroute_placement(pdm,cem,config=None):
    config=config or LayoutConfig()
    config.wire_clearance=pdm.validation_policy.wire_clearance_mm
    # All dependent routes are invalidated before attempting regeneration. The
    # duct network is a coupled capacity problem, so this version reroutes it all.
    pdm.routes=[]
    try:
        if any(abs(c.rotation_deg)%360>1e-6 for c in pdm.components):
            raise ValueError('Rotated-device obstacle routing is not supported; restore zero rotation.')
        pdm.routes=DuctRouter(config).route_layout(SimpleNamespace(components=pdm.components,rails=pdm.rails),
            cem.nets,pdm.enclosure_width,pdm.enclosure_height,pdm.enclosure_depth,ducts=pdm.ducts)
        failures=ValidationEngine().validate_pdm(pdm,cem,config)
        if failures:
            pdm.routes=[];pdm.validation_results=failures;return pdm
        for route in pdm.routes:
            route.geometry=build_wire_geometry(route,pdm);route.validation_checks=route.geometry.checks
        pdm.validation_results=[]
    except (RoutePlanningError,ValueError) as exc:
        pdm.routes=[]
        pdm.validation_results=[ValidationViolation(type='ROUTING',severity='CRITICAL',object_a=pdm.id,
            required_value=1,actual_value=0,unit='valid routes',message=str(exc))]
    return pdm
