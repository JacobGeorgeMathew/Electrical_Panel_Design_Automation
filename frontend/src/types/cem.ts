export interface RequirementItem {
  id: string;
  label: string;
  value: any;
  unit?: string;
  state: 'MISSING' | 'PROPOSED' | 'CONFIRMED' | 'VALIDATED' | 'DERIVED' | 'CALCULATED' | 'ASSUMED' | 'CONFLICTING';
  source: 'USER' | 'DEFAULT' | 'DERIVED' | 'SYSTEM';
  message?: string;
}

export interface ComponentRef {
  id: string;
  catalog_id: string;
  name: string;
  category: string;
  current_rating: number;
  breaking_capacity: number;
  poles: number;
  width: number;
  height: number;
  depth: number;
  mounting: string;
  heat_loss: number;
  cad_model: string;
  quantity: number;
}

export interface ConnectionRef {
  id: string;
  from_component: string;
  from_terminal: string;
  to_component: string;
  to_terminal: string;
  net_id: string;
  wire_class: string;
}

export interface NetRef {
  id: string;
  name: string;
  voltage_level: number;
  wire_class: 'POWER' | 'CONTROL' | 'SIGNAL' | 'PE' | 'NEUTRAL';
  connections: ConnectionRef[];
}

export interface CalculationResult {
  id: string;
  type: string;
  label: string;
  value: number;
  unit: string;
  formula_used: string;
  status: 'VALID' | 'WARNING' | 'CRITICAL';
  notes?: string;
}

export interface CanonicalEngineeringModel {
  project_id: string;
  panel_id: string;
  panel_type: string;
  revision: string;
  state: string;
  requirements: RequirementItem[];
  components: ComponentRef[];
  nets: NetRef[];
  calculations: CalculationResult[];
  physical_design_id?: string;
  dirty_nodes?: string[];
}
