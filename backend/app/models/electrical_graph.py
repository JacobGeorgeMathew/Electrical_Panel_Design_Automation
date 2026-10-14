from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ElectricalNode(BaseModel):
    id: str
    name: str
    type: str  # "PANEL", "INCOMER", "MCCB", "MCB", "SPD", "BUSBAR", "NEUTRAL_BAR", "EARTH_BAR", "TERMINAL", "LOAD"
    category: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class ElectricalEdge(BaseModel):
    source: str
    target: str
    relation: str  # "FEEDS", "PROTECTED_BY", "CONNECTED_TO", "TERMINATED_AT"
    wire_class: str = "POWER"
    properties: Dict[str, Any] = Field(default_factory=dict)


class ElectricalGraphModel(BaseModel):
    project_id: str
    nodes: List[ElectricalNode] = Field(default_factory=list)
    edges: List[ElectricalEdge] = Field(default_factory=list)
