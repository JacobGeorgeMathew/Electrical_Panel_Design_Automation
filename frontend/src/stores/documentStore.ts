/** Document adapter over the existing project editor. Workspace camera, selection
 * and visibility are intentionally absent from document persistence contracts. */
import { useProjectStore, type ProjectState } from './projectStore';
import type { DocumentSave, DocumentView } from '../types/document';
import type { ProjectConfiguration } from '../types/api';
import type {PhysicalDesignModel} from '../types/pdm';
import type {CanonicalEngineeringModel} from '../types/cem';
import {documentSchematicGraph} from '../components/schematic/schematicGraph';

/** Includes transient drafts that may not advance the durable document clock. */
export function documentDraftFingerprint(state: ProjectState) {
  return JSON.stringify([state.requirementValues, state.projectConfiguration,
    state.schematicData, state.editorTransforms, state.pendingEditorEdit]);
}

export function recomputeAvailability(state: ProjectState) {
  const reason = !state.document ? 'Open a working document to recompute.'
    : state.viewedRevisionId ? 'Historical revisions are read-only.'
    : state.isLoadingProject || state.isSaving || state.isGenerating ? 'Wait for the current document request.'
    : state.pendingRecovery ? 'Resolve recovery before recomputing.'
    : state.hasUnsavedChanges || Object.keys(state.editorTransforms).length || state.pendingEditorEdit ||
      JSON.stringify(state.schematicData) !== JSON.stringify(documentSchematicGraph(state.document))
      ? 'Save input drafts and finish or discard transient edits before recomputing.'
    : null;
  return {unavailable: !!reason, reason};
}

export function documentFields(view: DocumentView) {
  if (view.document.schema_version !== '1.0.0') throw new Error('Unsupported working-document schema. Local data retained.');
  const values = Object.fromEntries(view.snapshots.requirements.items.map(item => [item.id, item.value]));
  // Backend snapshots are validated and retain nullable metadata. These legacy
  // viewer contracts consume the same geometry/IDs; no snapshot is written back.
  return { document: view, cem: view.snapshots.cem as unknown as CanonicalEngineeringModel | null,
    pdm: view.snapshots.pdm as unknown as PhysicalDesignModel | null,
    pdmBaseline: view.snapshots.pdm as unknown as PhysicalDesignModel | null,
    schematicData: documentSchematicGraph(view),
    editorTransforms: {}, pendingEditorEdit: null, editorUndoStack: [], editorRedoStack: [],
    requirementValues: values, savedRequirementValues: values,
    projectConfiguration: view.document.configuration as ProjectConfiguration,
    savedConfiguration: view.document.configuration as ProjectConfiguration,
    lockVersion: view.document.lock_version,
    recoveryBaseDocument: { document_id: view.document.document_id,
      document_sequence: view.document.document_sequence, schema_version: view.document.schema_version } };
}

export function documentSave(state: ProjectState): DocumentSave {
  const view = state.document;
  if (!view) throw new Error('Open a supported working document before saving.');
  const previous = view.snapshots.requirements;
  const items = Object.entries(state.requirementValues).map(([id, value]) => {
    const old = previous.items.find(item => item.id === id);
    if (old && JSON.stringify(old.value) === JSON.stringify(value)) return old;
    return { id, label: old?.label || id, value, unit: old?.unit || null,
      state: 'PROPOSED' as const, source: 'USER', message: null };
  });
  const changed = JSON.stringify(items) !== JSON.stringify(previous.items);
  return { schema_version: '1.0.0', document_id: view.document.document_id,
    expected_version: state.lockVersion, expected_document_sequence: view.document.document_sequence,
    requirements: changed ? { ...previous, items, is_valid: false, validation_errors: [], validation_warnings: [] } : previous,
    configuration: state.projectConfiguration };
}

/** Match the server's bounded legacy generation guard. This is not the future
 * Publish action, which must snapshot already recomputed output. */
export function publicationAvailability(state: ProjectState) {
  const view = state.document;
  const needsProposal = !!view && (view.document.document_sequence > 0 ||
    view.snapshots.cem !== null || !!view.document.generation_intent);
  const reason = state.viewedRevisionId ? 'Historical revisions are read-only.'
    : needsProposal ? 'Publication of edited working documents is unavailable. Use separate Recompute and Publish steps: Recompute is available in the workspace; proposal acceptance changes only the working draft. Save preserves your edits.'
    : view && state.hasUnsavedChanges ? 'Save input drafts first. Changed-input Save requires the proposal workflow; publication of that edited document is unavailable.'
    : null;
  return { unavailable: !!reason, reason,
    label: reason ? 'Publish unavailable' : 'Generate & publish revision (legacy)' };
}

export function documentStatus(state: ProjectState) {
  const historical = !!state.viewedRevisionId;
  const unsupported = state.publishedDesign?.output_status === 'MISSING_OUTPUTS';
  const source = state.publishedDesign?.output_manifest?.source_document;
  const overlay = Object.keys(state.editorTransforms).length > 0 ||
    JSON.stringify(state.schematicData) !== JSON.stringify(state.document ? documentSchematicGraph(state.document) : state.publishedDesign?.schematic ?? null);
  const publishedValues = Object.fromEntries((state.publishedDesign?.cem.requirements || []).map(item=>[item.id,item.value]));
  const inputsDiffer = !!state.document && Object.entries(state.requirementValues)
    .some(([key,value])=>JSON.stringify(value)!==JSON.stringify(publishedValues[key]));
  const dirtyOutput = state.designStale || overlay || inputsDiffer || (state.document && (!source || source.sha256 !== state.document.content_sha256));
  return { readOnly: historical, unsupported, dirtyOutput: !!dirtyOutput,
    saveLabel: historical ? 'Historical read-only' : state.hasUnsavedChanges ? 'Unsaved draft' : 'Saved draft',
    outputLabel: unsupported ? 'Unsupported legacy output · missing saved representations'
      : historical ? `Historical read-only · r${state.currentRevisionNo}`
      : dirtyOutput ? 'Dirty engineering output · Recompute required before Publish'
      : state.currentRevisionNo ? `Active revision r${state.currentRevisionNo}` : 'No published output' };
}

export function useDocumentStore() {
  const state = useProjectStore();
  return { ...documentStatus(state), document: state.document,
    publication: publicationAvailability(state), save: state.saveCurrentProject, publish: state.runDesignPipeline };
}
