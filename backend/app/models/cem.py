from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.requirements import RequirementItem
from app.models.electrical_graph import ElectricalGraphModel


class CEMState(str, Enum):
    DRAFT = "DRAFT"
    REQUIREMENTS_VALIDATED = "REQUIREMENTS_VALIDATED"
    ENGINEERING_CALCULATED = "ENGINEERING_CALCULATED"
    COMPONENTS_SELECTED = "COMPONENTS_SELECTED"
    NETLIST_VALIDATED = "NETLIST_VALIDATED"
    SCHEMATIC_GENERATED = "SCHEMATIC_GENERATED"
    PHYSICAL_DESIGN_GENERATED = "PHYSICAL_DESIGN_GENERATED"
    LAYOUT_VALIDATED = "LAYOUT_VALIDATED"
    FINAL_VALIDATED = "FINAL_VALIDATED"


class FunctionalModule(BaseModel):
    id: str
    name: str
    category: str
    required: bool = True
    assigned_component_id: Optional[str] = None


class LoadItem(BaseModel):
    id: str
    name: str
    power_kw: float
    current_a: float
    phase_type: str  # "1P", "3P"
    power_factor: float = 0.85


class ComponentRef(BaseModel):
    id: str
    catalog_id: str
    component_version_id: Optional[str] = None
    product_version_id: Optional[str] = None
    cad_model_version_id: Optional[str] = None
    name: str
    category: str
    current_rating: float
    breaking_capacity: float
    poles: int
    width: float
    height: float
    depth: float
    mounting: str
    heat_loss: float
    cad_model: str
    quantity: int = 1
    terminals: List[Dict[str, Any]] = Field(default_factory=list)


class ConnectionRef(BaseModel):
    id: str
    from_component: str
    from_terminal: str
    to_component: str
    to_terminal: str
    net_id: str
    wire_class: str = "POWER"


class NetRef(BaseModel):
    id: str
    name: str
    voltage_level: float
    wire_class: str  # "POWER", "CONTROL", "SIGNAL", "PE", "NEUTRAL"
    connections: List[ConnectionRef] = Field(default_factory=list)


class CalculationResult(BaseModel):
    id: str
    type: str
    label: str
    value: float
    unit: str
    formula_used: str
    status: str = "VALID"
    notes: Optional[str] = None


class EngineeringConstraint(BaseModel):
    id: str
    category: str
    name: str
    limit_value: float
    actual_value: float
    unit: str
    passed: bool
    severity: str = "WARNING"  # "INFO", "WARNING", "CRITICAL"


class ComplianceItem(BaseModel):
    rule_id: str
    rule_name: str
    passed: bool
    details: str


class CanonicalEngineeringModel(BaseModel):
    project_id: str
    panel_id: str
    panel_type: str = "DB"
    revision: str = "1.0.0"
    state: CEMState = CEMState.DRAFT
    
    requirements: List[RequirementItem] = Field(default_factory=list)
    modules: List[FunctionalModule] = Field(default_factory=list)
    loads: List[LoadItem] = Field(default_factory=list)
    components: List[ComponentRef] = Field(default_factory=list)
    electrical_graph: Optional[ElectricalGraphModel] = None
    connections: List[ConnectionRef] = Field(default_factory=list)
    nets: List[NetRef] = Field(default_factory=list)
    calculations: List[CalculationResult] = Field(default_factory=list)
    constraints: List[EngineeringConstraint] = Field(default_factory=list)
    compliance: List[ComplianceItem] = Field(default_factory=list)
    
    physical_design_id: Optional[str] = None
    dirty_nodes: List[str] = Field(default_factory=list)
