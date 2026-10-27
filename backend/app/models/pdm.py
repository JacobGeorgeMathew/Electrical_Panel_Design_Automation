from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Position3D(BaseModel):
    x: float
    y: float
    z: float


class PhysicalZone(BaseModel):
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float = 0.0
    z_max: float = 300.0


class EnclosureSpec(BaseModel):
    id: str
    name: str
    width: float
    height: float
    depth: float
    ip_rating: str
    mounting_plate_width: float
    mounting_plate_height: float
    mounting_plate_offset_x: float
    mounting_plate_offset_y: float
    mounting_plate_offset_z: float
    max_thermal_dissipation: float
    zones: List[PhysicalZone] = Field(default_factory=list)


class PhysicalComponent(BaseModel):
    id: str  # PDM component ID (e.g., PDM-QF001)
    cem_component_id: str  # References CEM component (e.g., QF001)
    name: str
    category: str
    position: Position3D
    width: float
    height: float
    depth: float
    rotation_deg: float = 0.0
    rail_id: Optional[str] = None
    zone_name: str
    heat_loss_watts: float
    cad_model: str
    cad_model_version_id: Optional[str] = None
    preview_asset: Optional[Dict[str, Any]] = None
    color_hex: str = "#3B82F6"
    terminals: List[Dict[str, Any]] = Field(default_factory=list)


class DINRail(BaseModel):
    id: str
    label: str
    x: float
    y: float
    z: float
    length: float
    profile_height: float = 7.5
    profile_depth: float = 35.0
    orientation: str = "HORIZONTAL"  # "HORIZONTAL", "VERTICAL"


class CableDuct(BaseModel):
    id: str
    label: str
    x: float
    y: float
    z: float
    width: float
    height: float
    depth: float
    capacity_pct: float = 0.0


class BusbarAssembly(BaseModel):
    id: str
    label: str
    x: float
    y: float
    z: float
    width: float
    height: float
    depth: float
    rating_a: float


class Waypoint3D(BaseModel):
    x: float
    y: float
    z: float


class WireRoute(BaseModel):
    id: str
    net_id: str
    net_name: str
    from_component: str
    from_terminal: str
    to_component: str
    to_terminal: str
    wire_class: str  # "POWER", "CONTROL", "PE", "NEUTRAL"
    waypoints: List[Waypoint3D] = Field(default_factory=list)
    length_mm: float
    bend_count: int
    color_hex: str = "#EF4444"


class ClearanceEnvelope(BaseModel):
    component_id: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


class ValidationViolation(BaseModel):
    type: str  # "CLEARANCE", "OVERLAP", "BOUNDARY", "THERMAL", "DUCT_CAPACITY"
    severity: str  # "CRITICAL", "WARNING", "INFO"
    object_a: str
    object_b: Optional[str] = None
    required_value: float
    actual_value: float
    unit: str
    message: str


class PhysicalDesignModel(BaseModel):
    id: str
    project_id: str
    panel_id: str
    enclosure_id: str
    enclosure_width: float
    enclosure_height: float
    enclosure_depth: float
    ip_rating: str
    mounting_plate_x: float = 0.0
    mounting_plate_y: float = 0.0
    mounting_plate_z: float = 0.0
    mounting_plate_width: Optional[float] = None
    mounting_plate_height: Optional[float] = None
    
    zones: List[PhysicalZone] = Field(default_factory=list)
    components: List[PhysicalComponent] = Field(default_factory=list)
    rails: List[DINRail] = Field(default_factory=list)
    ducts: List[CableDuct] = Field(default_factory=list)
    busbars: List[BusbarAssembly] = Field(default_factory=list)
    routes: List[WireRoute] = Field(default_factory=list)
    clearances: List[ClearanceEnvelope] = Field(default_factory=list)
    validation_results: List[ValidationViolation] = Field(default_factory=list)
    
    total_heat_loss_watts: float = 0.0
    thermal_density_index: float = 0.0
