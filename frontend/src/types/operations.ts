/** Pure preview only; these contracts grant no apply or approval authority. */
import type { DirtyStage, DocumentProvenance, ResolvedDocument } from './document';

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
  preconditions: { snapshot_sha256: string };
}

export type Operation = OperationBase & (
  | { type: 'MoveComponent'; target: { cem_component_id: string; pdm_component_id: string };
      parameters: { position_mm: { x: number; y: number; z: number } }; affected_models?: ['pdm'] }
  | { type: 'UpdateRequirement'; target: { requirement_id: string };
      parameters: { value: number | string | boolean | null }; affected_models?: ['requirements'] }
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

export interface OperationPreview {
  batch_id: string;
  status: 'PREVIEW';
  persisted: false;
  base_sequence: number;
  before_content_sha256: string;
  after_content_sha256: string;
  changes: { operation_id: string; model: 'requirements' | 'pdm'; target_id: string;
    before_sha256: string; after_sha256: string;
    changed_fields: ('position_mm' | 'terminals_mm' | 'value' | 'state' | 'source' | 'message' | 'validation')[] }[];
  required_checks: { code: 'requirement_rules' | 'physical_constraints' | 'routing' | 'physical_validation';
    status: 'UNRESOLVED' }[];
  dirty_stages: DirtyStage[];
  candidate: ResolvedDocument;
}
