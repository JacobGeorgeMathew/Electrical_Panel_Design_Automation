import type { ProjectConfiguration } from './api';
import type { EditorTransform } from '../stores/projectStore';

export interface RecoveryBaseDocument {
  document_id: string;
  document_sequence: number;
  schema_version: '1.0.0';
}

export interface RecoveryDocument {
  /** Absent in existing checkpoints. Unknown versions remain available for review. */
  schema_version?: number;
  baseDocument?: RecoveryBaseDocument | null;
  requirements: Record<string, any>;
  configuration: ProjectConfiguration;
  workspace: { editorTransforms?: Record<string, EditorTransform>; schematicData?: any };
  baseRevisionId: string | null;
}

export interface Checkpoint {
  schema_version?: number;
  /** Server recovery clock, independent of project L and document S. */
  recovery_sequence?: number;
  base_version: number;
  saved_at: string;
  document: RecoveryDocument;
}
