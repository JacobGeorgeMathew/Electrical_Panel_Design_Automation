"""Single-page presentation in schematic mm; CEM remains connectivity authority.

This is a new persisted contract, not the legacy SchematicEngine dictionary.
Crossings, symbol placement and waypoints cannot create electrical connections.
"""
from typing import Literal

from pydantic import Field, model_validator

from app.models.identity import ContractModel, StableID, require_reference, unique_ids


class SchematicPoint(ContractModel):
    x: float
    y: float


class SchematicPin(ContractModel):
    id: StableID
    terminal_id: StableID
    position: SchematicPoint
    direction: Literal['TOP', 'BOTTOM', 'LEFT', 'RIGHT']
    label: str = ''


class SchematicSymbol(ContractModel):
    id: StableID
    component_id: StableID
    position: SchematicPoint
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    rotation_deg: float = 0
    label: str = ''
    pins: list[SchematicPin] = Field(default_factory=list)


class SchematicWire(ContractModel):
    id: StableID
    conductor_id: StableID
    source_pin_id: StableID
    target_pin_id: StableID
    waypoints: list[SchematicPoint] = Field(min_length=2)
    label: str = ''


class SchematicPresentation(ContractModel):
    schema_version: Literal['1.0.0'] = '1.0.0'
    id: StableID
    project_id: StableID
    panel_id: StableID
    page_id: StableID
    coordinate_system: Literal['schematic-mm-top-left'] = 'schematic-mm-top-left'
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    symbols: list[SchematicSymbol] = Field(default_factory=list)
    wires: list[SchematicWire] = Field(default_factory=list)

    @model_validator(mode='after')
    def presentation_references(self):
        unique_ids((symbol.id for symbol in self.symbols), 'schematic.symbols')
        pins = unique_ids((pin.id for symbol in self.symbols for pin in symbol.pins), 'schematic.pins')
        unique_ids((wire.id for wire in self.wires), 'schematic.wires')
        for wire in self.wires:
            require_reference(wire.source_pin_id, pins, f'wires.{wire.id}.source_pin_id')
            require_reference(wire.target_pin_id, pins, f'wires.{wire.id}.target_pin_id')
        return self
