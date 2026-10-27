export interface Position3D {
  x: number;
  y: number;
  z: number;
}

export interface PhysicalZone {
  name: string;
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  z_min?: number;
  z_max?: number;
}

export interface PhysicalComponent {
  id: string;
  cem_component_id: string;
  name: string;
  category: string;
  position: Position3D;
  width: number;
  height: number;
  depth: number;
  rotation_deg?: number;
  rail_id?: string;
  zone_name: string;
  heat_loss_watts: number;
  cad_model: string;
  cad_model_version_id?: string;
  preview_asset?: import('./api').Artifact | null;
  color_hex: string;
  terminals: { id: string; x: number; y: number; z: number; [key: string]: any }[];
}

export interface DINRail {
  id: string;
  label: string;
  x: number;
  y: number;
  z: number;
  length: number;
  profile_height: number;
  profile_depth: number;
  orientation?: string;
}

export interface Waypoint3D {
  x: number;
  y: number;
  z: number;
}

export interface WireRoute {
  id: string;
  net_id: string;
  net_name: string;
  from_component: string;
  from_terminal: string;
  to_component: string;
  to_terminal: string;
  wire_class: 'POWER' | 'CONTROL' | 'PE' | 'NEUTRAL';
  waypoints: Waypoint3D[];
  length_mm: number;
  bend_count: number;
  color_hex: string;
}

export interface ValidationViolation {
  type: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  object_a: string;
  object_b?: string;
  required_value: number;
  actual_value: number;
  unit: string;
  message: string;
}

export interface PhysicalDesignModel {
  id: string;
  project_id: string;
  panel_id: string;
  enclosure_id: string;
  enclosure_width: number;
  enclosure_height: number;
  enclosure_depth: number;
  ip_rating: string;
  mounting_plate_x: number;
  mounting_plate_y: number;
  mounting_plate_z: number;
  mounting_plate_width?: number;
  mounting_plate_height?: number;
  zones: PhysicalZone[];
  components: PhysicalComponent[];
  rails: DINRail[];
  routes: WireRoute[];
  validation_results: ValidationViolation[];
  total_heat_loss_watts: number;
  thermal_density_index: number;
}
