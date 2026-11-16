import {useProjectStore} from './projectStore';
import {useCommandStore} from './commandStore';
import {fetchOperationHistory} from '../api/client';
import type {Operation, OperationOrigin} from '../types/operations';

export const manualOrigin: OperationOrigin = {kind: 'MANUAL', actor_id: 'workspace-user'};
type Intent = Operation extends infer O ? O extends Operation ? Omit<O, 'operation_id' | 'origin' | 'preconditions'> : never : never;

export function canEditEngineering() {
  const s = useProjectStore.getState(), c = useCommandStore.getState();
  return !!s.document && !s.viewedRevisionId && !s.isLoadingProject && !s.isSaving &&
    !s.isGenerating && !s.pendingRecovery && !c.pending && !c.proposal;
}

/** Capture every affected hash from the loaded base; callers supply intents only. */
export function proposeOperation(intent: Intent, models: ('cem' | 'pdm' | 'schematic')[]) {
  if (!canEditEngineering()) return false;
  const s = useProjectStore.getState(), view = s.document!;
  const hashes = Object.fromEntries(models.map(k => [k, view.document.models[k]?.sha256 ?? null]));
  const operation = {...intent, operation_id: crypto.randomUUID(), origin: manualOrigin,
    preconditions: {snapshot_sha256: view.document.models[models[0]]!.sha256, model_sha256: hashes}} as Operation;
  useCommandStore.getState().propose({kind: 'operations', projectId: s.projectId, key: crypto.randomUUID(), request: {
    schema_version: '1.0.0', batch_id: crypto.randomUUID(), document_id: view.document.document_id,
    base_sequence: view.document.document_sequence, expected_version: s.lockVersion,
    base_revision_id: view.document.base_revision_id, operations: [operation],
  }});
  return true;
}

export async function commitPlacement() {
  const s = useProjectStore.getState();
  if (!canEditEngineering()) return;
  if (s.pdm?.components.some(c=>s.editorTransforms[c.cem_component_id]&&
      s.editorTransforms[c.cem_component_id].rotation_deg !== (c.rotation_deg||0))) {
    s.setError('Rotation is unsupported. Discard the rotated preview before moving.');return;
  }
  const changed = s.pdm?.components.filter(c => {
    const t = s.editorTransforms[c.cem_component_id];
    return t && (t.x !== c.position.x || t.y !== c.position.y || t.z !== c.position.z);
  }) || [];
  // Each gesture owns one component and one history group.
  if (changed.length !== 1) {s.resetEditorDraft(); return;}
  const c = changed[0], t = s.editorTransforms[c.cem_component_id];
  if (proposeOperation({type: 'MoveComponent', target: {cem_component_id: c.cem_component_id, pdm_component_id: c.id},
    parameters: {position_mm: {x: t.x, y: t.y, z: t.z}}}, ['pdm']))
    await useCommandStore.getState().commitProposal();
}

export async function applyHistory(action: 'UNDO' | 'REDO') {
  if (!canEditEngineering()) return;
  const s = useProjectStore.getState(), view = s.document!;
  try {
    const history = await fetchOperationHistory(s.projectId);
    if (useProjectStore.getState().document !== view || !canEditEngineering()) return;
    const target = (action === 'UNDO' ? history.undo_batch_ids : history.redo_batch_ids).at(-1);
    if (!target) return;
    useCommandStore.getState().propose({kind: 'history', projectId: s.projectId, key: crypto.randomUUID(), request: {
      schema_version: '1.0.0', batch_id: crypto.randomUUID(), operation_id: crypto.randomUUID(),
      origin: manualOrigin, document_id: view.document.document_id,
      base_sequence: view.document.document_sequence, expected_version: s.lockVersion,
      base_revision_id: view.document.base_revision_id, before_content_sha256: view.content_sha256,
      action, target_batch_id: target,
    }});
    await useCommandStore.getState().commitProposal();
  } catch (error) {s.setError(error instanceof Error ? error.message : String(error));}
}
