import type { ProjectConfiguration } from '../types/api';
import type { EditorTransform } from './projectStore';
export interface RecoveryDocument {
  requirements: Record<string, any>;
  configuration: ProjectConfiguration;
  workspace: { editorTransforms?: Record<string, EditorTransform>; schematicData?: any };
  baseRevisionId: string | null;
}
export interface Checkpoint { base_version: number; saved_at: string; document: RecoveryDocument; }
const key = (id: string) => `panelstudio:recovery:v1:${id}`;
export function readRecovery(id: string): Checkpoint | null {
  try { const value=JSON.parse(localStorage.getItem(key(id)) || 'null');
    return value?.document?.requirements && value?.document?.configuration && value?.document?.workspace ? value : null;
  } catch { return null; }
}
export function writeRecovery(id: string, checkpoint: Checkpoint) { localStorage.setItem(key(id), JSON.stringify(checkpoint)); }
export function clearRecovery(id: string) { localStorage.removeItem(key(id)); }
