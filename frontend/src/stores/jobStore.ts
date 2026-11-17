import {create} from 'zustand';
import {persist} from 'zustand/middleware';
import {submitRecomputeJob, listRecomputeJobs, fetchRecomputeJob,
  cancelRecomputeJob, acceptGenerationProposal} from '../api/client';
import type {RecomputeJob, RecomputeJobRequest} from '../types/jobs';
import {useProjectStore} from './projectStore';
import {useCommandStore} from './commandStore';
import {documentFields, documentDraftFingerprint, recomputeAvailability} from './documentStore';

interface Tracking {
  request: RecomputeJobRequest;
  key: string;
  acceptKey: string;
  jobId?: string;
  baseSha256: string;
  fingerprint: string | null;
  applied?: boolean;
}
interface JobStore {
  tracking: Record<string, Tracking>;
  jobs: Record<string, RecomputeJob>;
  errors: Record<string, string | null>;
  statusErrors: Record<string, string | null>;
  pending: Record<string, boolean>;
  submit: (retry?: boolean) => Promise<void>;
  refresh: (projectId: string, signal?: AbortSignal) => Promise<void>;
  cancel: (projectId: string) => Promise<void>;
  apply: (projectId: string) => Promise<void>;
}
export const jobActive = (job?: RecomputeJob) => job?.state === 'QUEUED' || job?.state === 'RUNNING';
const message = (error: unknown) => error instanceof Error ? error.message : 'Job request failed. Tracking retained.';

/** Completion never writes editor state. Only explicit, base-fenced acceptance
 * installs a server document; published revisions and display state stay separate. */
export const useJobStore = create<JobStore>()(persist((set, get) => {
  const error = (projectId: string, value: string | null) => set(s => ({errors: {...s.errors, [projectId]: value}}));
  const statusError = (projectId: string, value: string | null) => set(s => ({statusErrors: {...s.statusErrors, [projectId]: value}}));
  const pending = (projectId: string, value: boolean) => set(s => ({pending: {...s.pending, [projectId]: value}}));
  const track = (projectId: string, value: Tracking) => set(s => ({tracking: {...s.tracking, [projectId]: value}}));
  const receive = (projectId: string, job: RecomputeJob) => {
    const previous = get().jobs[projectId];
    if (previous?.id === job.id && (previous.updated_at > job.updated_at ||
      (!jobActive(previous) && jobActive(job)))) return;
    set(s => ({jobs: {...s.jobs, [projectId]: job}}));
  };
  const send = async (projectId: string, intent: Tracking, signal?: AbortSignal) => {
    const job = await submitRecomputeJob(projectId, intent.request, intent.key, signal);
    if (get().tracking[projectId]?.key !== intent.key) return;
    track(projectId, {...intent, jobId: job.id});
    receive(projectId, job);
  };
  return {
    tracking: {}, jobs: {}, errors: {}, statusErrors: {}, pending: {},
    submit: async (retry = false) => {
      const state = useProjectStore.getState(), projectId = state.projectId;
      if (get().pending[projectId]) return;
      const command = useCommandStore.getState();
      const availability = recomputeAvailability(state);
      if (availability.unavailable || command.pending || command.proposal) {
        error(projectId, availability.reason || 'Finish the retained engineering proposal first.'); return;
      }
      const old = get().tracking[projectId], job = get().jobs[projectId];
      if (jobActive(job)) return;
      // An uncertain submission reuses the persisted intent/key. Explicit retry
      // after a terminal outcome is a new job against the currently saved base.
      if (retry && old?.jobId && !job) {
        error(projectId, 'Refresh job status before retrying.'); return;
      }
      const view = state.document!;
      const intent: Tracking = old && !old.jobId && !retry ? old : {
        request: {document_id: view.document.document_id,
          expected_document_sequence: view.document.document_sequence, expected_version: state.lockVersion},
        key: crypto.randomUUID(), acceptKey: crypto.randomUUID(), baseSha256: view.content_sha256,
        fingerprint: documentDraftFingerprint(state),
      };
      track(projectId, intent); pending(projectId, true); error(projectId, null);
      try {await send(projectId, intent);}
      catch (e) {error(projectId, message(e));}
      finally {pending(projectId, false);}
    },
    refresh: async (projectId, signal) => {
      if (get().pending[projectId]) return;
      try {
        const intent = get().tracking[projectId];
        if (intent) {
          if (!intent.jobId) await send(projectId, intent, signal);
          else {
            const job = await fetchRecomputeJob(projectId, intent.jobId, signal);
            if (!signal?.aborted && get().tracking[projectId]?.key === intent.key) receive(projectId, job);
          }
        } else {
          const rows = await listRecomputeJobs(projectId, signal);
          if (signal?.aborted || get().tracking[projectId]) return;
          const job = rows[0];
          if (job) {
            // Recovery from another tab/browser is conservative: explicit apply
            // still verifies the saved base and all local draft state.
            const state = useProjectStore.getState();
            track(projectId, {jobId: job.id, key: crypto.randomUUID(), acceptKey: crypto.randomUUID(),
              request: {document_id: job.document_id, expected_document_sequence: job.base_sequence,
                expected_version: job.base_version}, baseSha256: job.base_sha256,
              fingerprint: state.projectId === projectId && !recomputeAvailability(state).unavailable
                ? documentDraftFingerprint(state) : null});
            receive(projectId, job);
          }
        }
        if (!signal?.aborted) statusError(projectId, null);
      } catch (e) {if (!signal?.aborted) statusError(projectId, message(e));}
    },
    cancel: async projectId => {
      const intent = get().tracking[projectId];
      if (!intent?.jobId || get().pending[projectId]) return;
      pending(projectId, true); error(projectId, null);
      try {
        const job = await cancelRecomputeJob(projectId, intent.jobId);
        if (get().tracking[projectId]?.key === intent.key) receive(projectId, job);
      } catch (e) {error(projectId, message(e));}
      finally {pending(projectId, false);}
    },
    apply: async projectId => {
      const intent = get().tracking[projectId], job = get().jobs[projectId];
      const state = useProjectStore.getState(), view = state.document;
      const batch = job?.result?.response?.batch;
      if (!intent || intent.applied || !batch || job?.state !== 'SUCCEEDED' || get().pending[projectId]) return;
      if (state.projectId !== projectId || !view || recomputeAvailability(state).unavailable ||
        useCommandStore.getState().pending || useCommandStore.getState().proposal ||
        view.document.document_id !== intent.request.document_id ||
        view.document.document_sequence !== intent.request.expected_document_sequence ||
        state.lockVersion !== intent.request.expected_version || view.content_sha256 !== intent.baseSha256 ||
        documentDraftFingerprint(state) !== intent.fingerprint) {
        error(projectId, 'Recompute base changed. Local drafts retained; recompute the saved current document.'); return;
      }
      pending(projectId, true); error(projectId, null);
      useProjectStore.setState({isSaving: true});
      try {
        const receipt = await acceptGenerationProposal(projectId, batch, intent.acceptKey);
        const current = useProjectStore.getState();
        if (current.projectId === projectId && current.document === view &&
          current.lockVersion === state.lockVersion && current.editSequence === state.editSequence &&
          !current.hasUnsavedChanges && !current.pendingRecovery && !current.viewedRevisionId &&
          documentDraftFingerprint(current) === intent.fingerprint) {
          useProjectStore.setState({...documentFields(receipt.result), designStale: true});
        } else error(projectId, 'Proposal accepted on the server. Newer editor state retained; reopen after resolving local drafts.');
        track(projectId, {...intent, applied: true});
      } catch (e) {error(projectId, message(e));}
      finally {
        if (useProjectStore.getState().projectId === projectId) useProjectStore.setState({isSaving: false});
        pending(projectId, false);
      }
    },
  };
}, {name: 'panelflow-recompute-jobs-v1', partialize: state => ({tracking: state.tracking})}));

/** One non-overlapping poll loop per mounted workspace. Transport cancellation
 * stops polling only; the Cancel job action revokes the durable server job. */
export function pollDocumentJobs(projectId: string, interval = 1000) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  const tick = async () => {
    await useJobStore.getState().refresh(projectId, controller.signal);
    if (!controller.signal.aborted) timer = setTimeout(tick, interval);
  };
  void tick();
  return () => {controller.abort(); clearTimeout(timer);};
}
