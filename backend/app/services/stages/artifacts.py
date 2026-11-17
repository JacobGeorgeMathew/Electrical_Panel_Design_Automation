"""Detached BOM and eligible CAD payloads; content-addressed publication is I/O.

The caller owns asset hashing/storage and revision transactions. CAD requires the
schematic dependency and rechecks physical inputs instead of trusting saved PASS
flags. Native FreeCAD/STEP execution remains separate from script generation.
"""
from typing import Any, Literal

from app.models.identity import StableID
from app.services.cad_engine import CADEngine
from app.services.panel_assembly import assembly_bom
from app.services.stages.contracts import FrozenContract
from app.services.stages.electrical import Snapshot
from app.services.stages.physical import (
    PhysicalInput, PhysicalSnapshot, PhysicalValidationInput, _cem, _ownership, physical_validation_stage,
)


class BOMInput(PhysicalInput):
    algorithm_version: Literal['db-bom-1'] = 'db-bom-1'
    pdm: PhysicalSnapshot


class BOMOutput(FrozenContract):
    bom: Snapshot[list[dict[str, Any]]]


class CADInput(PhysicalInput):
    algorithm_version: Literal['db-cad-1'] = 'db-cad-1'
    pdm: PhysicalSnapshot
    schematic: Snapshot[dict[str, Any]]
    generator_version: StableID
    model_versions: Snapshot[dict[str, str]]
    include_freecad_script: bool = False


class CADOutput(FrozenContract):
    cad: Snapshot[dict[str, Any]]
    freecad_script: str | None = None


def bom_stage(inputs: BOMInput) -> BOMOutput:
    cem, pdm = _cem(inputs), inputs.pdm.read()
    _ownership(cem, pdm)
    return BOMOutput(bom=Snapshot[list[dict[str, Any]]].capture(assembly_bom(cem, pdm)))


def cad_stage(inputs: CADInput) -> CADOutput:
    validated = physical_validation_stage(PhysicalValidationInput(
        context=inputs.context, cem=inputs.cem, pdm=inputs.pdm))
    pdm = validated.pdm.read()
    engine = CADEngine()
    return CADOutput(cad=Snapshot[dict[str, Any]].capture(engine.generate_parametric_geometry(pdm)),
        freecad_script=engine.export_freecad_script(pdm) if inputs.include_freecad_script else None)
