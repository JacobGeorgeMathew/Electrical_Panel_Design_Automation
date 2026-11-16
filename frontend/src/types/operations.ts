/** Pure preview only; these contracts grant no apply or approval authority. */
import type { DirtyStage, DocumentProvenance, ResolvedDocument, SchematicPoint } from './document';

export interface OperationOrigin {
  kind: DocumentProvenance['origin'];
  actor_id: string;
  proposal_id?: string | null;
  job_id?: string | null;
}

interface OperationBase {
  operation_id: string;
  origin: OperationOrigin;
  proposal_status?: 'NOT_PROPOSED' | 'PROPOSED';
  preconditions: { snapshot_sha256: string; model_sha256?: Partial<Record<'requirements' | 'cem' | 'pdm' | 'schematic', string | null>> };
}

export interface CascadeConfirmation { dependencies: Record<string, string[]>; sha256: string }

export interface ConductorIntent {
  from_component: string; from_terminal: string; to_component: string; to_terminal: string; net_id: string;
  wire_class: 'POWER' | 'CONTROL' | 'SIGNAL' | 'PE' | 'NEUTRAL'; conductor_material: 'COPPER' | 'ALUMINIUM';
  cross_section_mm2: number; insulation_diameter_mm: number; insulation_type: string; minimum_bend_radius_mm: number;
}

export type Operation = OperationBase & (
  | { type: 'MoveComponent'; target: { cem_component_id: string; pdm_component_id: string };
      parameters: { position_mm: { x: number; y: number; z: number } }; affected_models?: ['pdm'] }
  | { type: 'RotateComponent'; target: { cem_component_id: string; pdm_component_id: string };
      parameters: { rotation_deg: number }; affected_models?: ['pdm'] }
  | { type: 'UpdateRequirement'; target: { requirement_id: string };
      parameters: { value: number | string | boolean | null }; affected_models?: ['requirements'] }
  | { type: 'ChangeComponentRating'; target: { cem_component_id: string };
      parameters: { catalog_id: string; component_version_id: string; current_rating: number }; affected_models?: ['cem'] }
  | { type: 'ResizeEnclosure'; target: { enclosure_id: string };
      parameters: { catalog_id: string; component_version_id: string; width: number; height: number; depth: number };
      affected_models?: ['pdm'] }
  | { type: 'AddComponent'; target: { panel_id: string };
      parameters: { catalog_id: string; component_version_id: string; product_version_id: string | null; terminal_intent: 'UNCONNECTED';
        terminal_ids: string[]; placement: { position_mm: { x: number; y: number; z: number }; zone_name: string; rail_id: string | null } };
      affected_models?: ['cem', 'pdm'] }
  | { type: 'RemoveComponent'; target: { cem_component_id: string };
      parameters: { confirmed_cascade?: CascadeConfirmation | null }; affected_models?: ['cem', 'pdm', 'schematic'] }
  | { type: 'MoveSymbol'; target: { symbol_id: string }; parameters: { position_mm: SchematicPoint }; affected_models?: ['schematic'] }
  | { type: 'UpdateSchematicLabel'; target: { kind: 'symbol' | 'wire' | 'pin'; id: string };
      parameters: { label: string }; affected_models?: ['schematic'] }
  | { type: 'UpdateJunctionPresentation'; target: { pin_id: string };
      parameters: { visible: boolean; label: string }; affected_models?: ['schematic'] }
  | { type: 'ModifyElectricalConnection'; target: { connection_id: string | null };
      parameters: { action: 'CREATE' | 'REPLACE' | 'DELETE'; conductor: ConductorIntent | null; invalidated_route_ids: string[]; removed_net_ids?: string[] };
      affected_models?: ['cem', 'pdm', 'schematic'] }
  | { type: 'RegenerateSchematic'; target: { schematic_id: string }; parameters: { replace_manual_positions?: boolean };
      affected_models?: ['schematic'] }
);

export interface OperationPreviewRequest {
  schema_version?: '1.0.0';
  batch_id: string;
  document_id: string;
  base_sequence: number;
  expected_version: number;
  base_revision_id: string | null;
  operations: Operation[];
}

export interface HistoryRequest {
  schema_version?: '1.0.0'; batch_id: string; operation_id: string; document_id: string;
  base_sequence: number; expected_version: number; base_revision_id: string | null;
  before_content_sha256: string; action: 'UNDO' | 'REDO'; target_batch_id: string; origin: OperationOrigin;
}

export interface OperationHistory {
  document_id: string; document_sequence: number; lock_version: number; content_sha256: string;
  undo_batch_ids: string[]; redo_batch_ids: string[];
}

export interface OperationPreview {
  batch_id: string;
  status: 'PREVIEW';
  persisted: false;
  base_sequence: number;
  before_content_sha256: string;
  after_content_sha256: string;
  consequences: Record<string, CascadeConfirmation>;
  changes: { operation_id: string; model: 'requirements' | 'cem' | 'pdm' | 'schematic'; target_id: string;
    before_sha256: string; after_sha256: string;
    changed_fields: ('position_mm' | 'terminals_mm' | 'rotation_deg' | 'value' | 'state' | 'source' | 'message' | 'validation' |
      'component_catalog' | 'enclosure_catalog' | 'components' | 'cascade' | 'presentation' | 'connections')[] }[];
  required_checks: { code: 'requirement_rules' | 'physical_constraints' | 'routing' | 'physical_validation';
    status: 'UNRESOLVED' }[];
  dirty_stages: DirtyStage[];
  candidate: ResolvedDocument;
}
