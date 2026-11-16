/** Versioned working document. Resolve and validate snapshots on the server.
 * IDs are opaque strings. Physical snapshots retain enclosure mm; schematic
 * points use schematic-mm-top-left. Neither presentation nor crossings own nets.
 */
import type { CanonicalEngineeringModel, ComponentRef, ConnectionRef, RequirementItem } from './cem';
import type { PhysicalDesignModel } from './pdm';

export type StableID = string;
export type SnapshotReference = { schema_version: 1; sha256: string };
export type DirtyStage = 'requirements' | 'calculations' | 'selection' | 'connectivity'
  | 'schematic' | 'placement' | 'routes' | 'physical_validation' | 'bom' | 'cad';

export interface DocumentReferences {
  requirements: SnapshotReference;
  cem: SnapshotReference | null;
  pdm: SnapshotReference | null;
  schematic: SnapshotReference | null;
}

export interface PinnedVersions {
  engine_version: string;
  generator: { name: string; version: string };
  catalog_manifest_sha256: string;
  validation_policy_version: string;
  catalog_versions: Record<string, string>;
  model_versions: Record<string, string>;
}

export interface DocumentProvenance {
  origin: 'MANUAL' | 'AUTOMATIC' | 'IMPORT' | 'RESTORE' | 'COMPATIBILITY' | 'AI_PROPOSAL';
  actor_id: StableID;
  last_operation_id: StableID | null;
  source_revision_id: StableID | null;
  proposal_id: StableID | null;
  job_id: StableID | null;
}

export interface WorkingDocument {
  schema_version: '1.0.0';
  document_id: StableID;
  project_id: StableID;
  panel_id: StableID;
  archetype: 'DB';
  document_sequence: number;
  lock_version: number;
  base_revision_id: StableID | null;
  models: DocumentReferences;
  configuration: Record<string, unknown>;
  pins: PinnedVersions;
  provenance: DocumentProvenance;
  dirty_stages: DirtyStage[];
  enclosure_interfaces: { component_id: StableID; terminal_ids: StableID[] }[];
}

export interface SchematicPoint { x: number; y: number }
export interface SchematicPin {
  id: StableID;
  terminal_id: StableID;
  position: SchematicPoint;
  direction: 'TOP' | 'BOTTOM' | 'LEFT' | 'RIGHT';
  label: string;
}
export interface SchematicSymbol {
  id: StableID;
  component_id: StableID;
  position: SchematicPoint;
  width_mm: number;
  height_mm: number;
  rotation_deg: number;
  label: string;
  pins: SchematicPin[];
}
export interface SchematicWire {
  id: StableID;
  conductor_id: StableID;
  source_pin_id: StableID;
  target_pin_id: StableID;
  waypoints: SchematicPoint[];
  label: string;
}
export interface SchematicPresentation {
  schema_version: '1.0.0';
  id: StableID;
  project_id: StableID;
  panel_id: StableID;
  page_id: StableID;
  coordinate_system: 'schematic-mm-top-left';
  width_mm: number;
  height_mm: number;
  symbols: SchematicSymbol[];
  wires: SchematicWire[];
  junctions?: { id: StableID; pin_id: StableID; visible: boolean; label: string }[];
}

// Snapshot views retain backend nullable values without changing legacy UI types.
export type DocumentRequirement = Omit<RequirementItem, 'value' | 'unit' | 'source' | 'message'> & {
  value: unknown; unit: string | null; source: string; message: string | null;
};
export interface RequirementSnapshot {
  project_id: StableID;
  archetype: string;
  items: DocumentRequirement[];
  is_valid: boolean;
  validation_errors: string[];
  validation_warnings: string[];
}
export type DocumentConnection = ConnectionRef & {
  conductor_material: string | null;
  cross_section_mm2: number | null;
  insulation_diameter_mm: number | null;
  insulation_type: string | null;
  minimum_bend_radius_mm: number | null;
};
export type CEMSnapshot = Omit<CanonicalEngineeringModel,
  'requirements' | 'physical_design_id' | 'electrical_graph' | 'components' | 'connections' | 'nets' | 'calculations'> & {
  requirements: DocumentRequirement[];
  physical_design_id: string | null;
  electrical_graph: NonNullable<CanonicalEngineeringModel['electrical_graph']> | null;
  modules: { id: string; name: string; category: string; required: boolean; assigned_component_id: string | null }[];
  loads: { id: string; name: string; power_kw: number; current_a: number; phase_type: string; power_factor: number }[];
  components: (Omit<ComponentRef, 'terminals'> & {
    component_version_id: string | null; product_version_id: string | null; cad_model_version_id: string | null;
    terminals: ({ id: string } & Record<string, unknown>)[];
  })[];
  connections: DocumentConnection[];
  nets: { id: string; name: string; voltage_level: number; wire_class: string; connections: DocumentConnection[] }[];
  calculations: { id: string; type: string; label: string; value: number; unit: string; formula_used: string;
    status: string; notes: string | null }[];
  constraints: { id: string; category: string; name: string; limit_value: number; actual_value: number;
    unit: string; passed: boolean; severity: string }[];
  compliance: { rule_id: string; rule_name: string; passed: boolean; details: string }[];
};
export type PDMSnapshot = Omit<PhysicalDesignModel,
  'components' | 'mounting_plate_width' | 'mounting_plate_height' | 'routes' | 'ducts' | 'accessories' | 'validation_results'> & {
  mounting_plate_width: number | null;
  mounting_plate_height: number | null;
  components: (Omit<PhysicalDesignModel['components'][number], 'rail_id' | 'cad_model_version_id' | 'preview_asset' | 'geometry' | 'terminals'> & {
    rail_id: string | null; cad_model_version_id: string | null;
    preview_asset: Record<string, unknown> | null; geometry: Record<string, unknown>[];
    terminals: ({ id: string } & Record<string, unknown>)[];
  })[];
  ducts: (Omit<NonNullable<PhysicalDesignModel['ducts']>[number], 'component_version_id'> & {
    component_version_id: string | null; allowed_wire_classes: string[];
  })[];
  accessories: (Omit<NonNullable<PhysicalDesignModel['accessories']>[number], 'component_version_id'> & {
    component_version_id: string | null;
  })[];
  routes: (Omit<PhysicalDesignModel['routes'][number], 'geometry' | 'duct_entry_index' | 'duct_exit_index' | 'conductor_id' | 'minimum_bend_radius_mm'> & {
    conductor_id: string | null; duct_entry_index: number | null; duct_exit_index: number | null;
    minimum_bend_radius_mm: number | null;
    geometry: {
      id: string; route_id: string; cad_object_id: string; centerline: { x: number; y: number; z: number }[];
      diameter_mm: number; centerline_length_mm: number; duct_entry_index: number | null; duct_exit_index: number | null;
      backend: string; status: string; bend_radii_mm: number[]; checks: Record<string, unknown>[];
    } | null;
    dimension_source: string; routing_algorithm: string; routing_config: Record<string, unknown>;
    status: string; validation_checks: Record<string, unknown>[];
  })[];
  busbars: { id: string; label: string; x: number; y: number; z: number; width: number; height: number;
    depth: number; rating_a: number }[];
  clearances: { component_id: string; x_min: number; x_max: number; y_min: number; y_max: number;
    z_min: number; z_max: number }[];
  validation_results: (Omit<PhysicalDesignModel['validation_results'][number], 'object_b'> & { object_b: string | null })[];
};
export interface DocumentSnapshots {
  requirements: RequirementSnapshot;
  cem: CEMSnapshot | null;
  pdm: PDMSnapshot | null;
  schematic: SchematicPresentation | null;
}
export interface ResolvedDocument {
  document: WorkingDocument;
  snapshots: DocumentSnapshots;
}

/** Explicit input Save. Generated models, display state and recovery are excluded. */
export interface DocumentSave {
  schema_version?: '1.0.0';
  document_id: StableID;
  expected_version: number;
  expected_document_sequence: number;
  requirements: RequirementSnapshot;
  configuration?: { enclosure_id?: string; enclosure_parameters?: Record<string, unknown> };
}

export interface DocumentView extends ResolvedDocument {
  content_sha256: string;
}
