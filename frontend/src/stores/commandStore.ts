import {create} from 'zustand';
import {ApiError, previewOperations, commitOperations, applyOperationHistory} from '../api/client';
import type {HistoryRequest, OperationPreviewRequest, OperationPreview, OperationCommit} from '../types/operations';
import {useProjectStore} from './projectStore';
import {documentFields} from './documentStore';
import {useWorkspaceStore} from './workspaceStore';

export type CommandProposal = {projectId: string; key: string} & (
  {kind: 'operations'; request: OperationPreviewRequest} | {kind: 'history'; request: HistoryRequest}
);
interface CommandState {
  proposal: CommandProposal | null;
  preview: OperationPreview | null;
  receipt: OperationCommit | null;
  error: ApiError | null;
  pending: boolean;
  propose: (proposal: CommandProposal) => void;
  previewProposal: () => Promise<void>;
  commitProposal: () => Promise<void>;
  cancel: () => void;
  clear: () => void;
}
let sequence = 0;
let controller: AbortController | null = null;

/** No optimistic model writes. Rejections/cancellation retain the exact proposal
 * and idempotency key, including when a commit response may have been lost. */
export const useCommandStore = create<CommandState>((set, get) => {
  const cancel = () => {
    sequence++;
    controller?.abort(); controller = null;
    set({pending: false});
  };
  const run = async (mode: 'preview' | 'commit') => {
    const proposal = get().proposal;
    if (!proposal) return;
    cancel();
    const token = sequence;
    const project = useProjectStore.getState();
    const base = project.document;
    const current = () => token === sequence && get().proposal === proposal &&
      useProjectStore.getState().projectId === project.projectId &&
      useProjectStore.getState().document === base &&
      useProjectStore.getState().lockVersion === project.lockVersion &&
      useProjectStore.getState().editSequence === project.editSequence;
    const fail = (error: unknown) => {
      if (!current()) return;
      set({error: error instanceof ApiError ? error : new ApiError('Command failed. Proposal retained.'), pending: false});
      useWorkspaceStore.getState().setBottomTab('output');
    };
    if (project.projectId !== proposal.projectId || !base || project.viewedRevisionId ||
        project.isLoadingProject || project.isSaving || project.isGenerating || project.pendingRecovery ||
        base.document.document_id !== proposal.request.document_id ||
        base.document.document_sequence !== proposal.request.base_sequence ||
        project.lockVersion !== proposal.request.expected_version ||
        base.document.base_revision_id !== proposal.request.base_revision_id) {
      fail(new ApiError('Command base changed or is read-only. Proposal retained; reload for comparison.', 409, 'DOCUMENT_CONFLICT'));
      return;
    }
    controller = new AbortController();
    set({pending: true, error: null});
    try {
      if (mode === 'preview') {
        if (proposal.kind !== 'operations') throw new ApiError('History is validated when applied.', 0, 'HISTORY_PREVIEW_UNSUPPORTED');
        const preview = await previewOperations(proposal.projectId, proposal.request, controller.signal);
        if (current()) set({preview, pending: false});
      } else {
        const receipt = proposal.kind === 'operations'
          ? await commitOperations(proposal.projectId, proposal.request, proposal.key, controller.signal)
          : await applyOperationHistory(proposal.projectId, proposal.request, proposal.key, controller.signal);
        if (!current()) return;
        // The working document advances; immutable published output is untouched.
        set({receipt, proposal: null, preview: null, pending: false});
        useProjectStore.setState({...documentFields(receipt.result), designStale: true,
          ...(project.hasUnsavedChanges ? {requirementValues: project.requirementValues,
            projectConfiguration: project.projectConfiguration} : {})});
      }
    } catch (error) { fail(error); }
    finally { if (token === sequence) {controller = null; set({pending: false});} }
  };
  return {proposal: null, preview: null, receipt: null, error: null, pending: false,
    propose: proposal => {cancel(); set({proposal: structuredClone(proposal), preview: null, receipt: null, error: null});},
    previewProposal: () => run('preview'), commitProposal: () => run('commit'), cancel,
    clear: () => {cancel(); set({proposal: null, preview: null, receipt: null, error: null});},
  };
});

useProjectStore.subscribe((state, previous) => {
  if (state.projectId !== previous.projectId || state.document !== previous.document ||
      state.editSequence !== previous.editSequence || state.viewedRevisionId !== previous.viewedRevisionId ||
      state.lockVersion !== previous.lockVersion || state.isLoadingProject !== previous.isLoadingProject ||
      state.isSaving !== previous.isSaving || state.isGenerating !== previous.isGenerating ||
      state.pendingRecovery !== previous.pendingRecovery)
    useCommandStore.getState().cancel();
});
