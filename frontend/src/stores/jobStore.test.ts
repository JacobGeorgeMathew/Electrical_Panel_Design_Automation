import {beforeEach, afterEach, describe, expect, it, vi} from 'vitest';
import fixture from '../types/fixtures/document-v1.json';
import batchFixture from '../types/fixtures/operation-preview-v1.json';
import type {DocumentView} from '../types/document';
import type {RecomputeJob} from '../types/jobs';
import {documentFields} from './documentStore';
import {useProjectStore} from './projectStore';
import {useCommandStore} from './commandStore';
import {useJobStore, pollDocumentJobs} from './jobStore';

const api = vi.hoisted(() => ({submitRecomputeJob: vi.fn(), listRecomputeJobs: vi.fn(),
  fetchRecomputeJob: vi.fn(), cancelRecomputeJob: vi.fn(), acceptGenerationProposal: vi.fn()}));
vi.mock('../api/client', async original => ({...await original<typeof import('../api/client')>(), ...api}));
const view = () => ({...structuredClone(fixture), content_sha256: 'a'.repeat(64)}) as DocumentView;
const job = (state: RecomputeJob['state'] = 'QUEUED'): RecomputeJob => ({
  id: 'job-1', document_id: 'document-1', base_sequence: 7, base_version: 3, base_sha256: 'a'.repeat(64),
  state, attempts: state === 'QUEUED' ? 0 : 1, max_attempts: 3, error: null,
  created_at: '2026-11-17T01:00:00Z', updated_at: '2026-11-17T01:00:00Z', result: null,
});
const complete = (): RecomputeJob => ({...job('SUCCEEDED'), result: {stage_executions: [], response: {
  status: 'REVIEW_REQUIRED', persisted: false, conflicts: [], batch: structuredClone(batchFixture) as any,
  preview: null, scheduled_stages: ['routes', 'physical_validation', 'cad'], stage_executions: [],
}}});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => {resolve = r;});
  return {promise, resolve};
};
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  useCommandStore.getState().clear();
  useJobStore.setState({tracking: {}, jobs: {}, errors: {}, statusErrors: {}, pending: {}});
  useProjectStore.setState({...documentFields(view()), projectId: 'project-1', editSequence: 0,
    hasUnsavedChanges: false, isLoadingProject: false, isSaving: false, isGenerating: false,
    pendingRecovery: null, viewedRevisionId: null});
  api.submitRecomputeJob.mockResolvedValue(job());
  api.fetchRecomputeJob.mockResolvedValue(job('RUNNING'));
  api.listRecomputeJobs.mockResolvedValue([]);
});
afterEach(() => {vi.useRealTimers();});

describe('durable recompute tracking', () => {
  it('acknowledges queued work, persists its base/key and resumes polling after rehydration without resubmitting', async () => {
    const original = useProjectStore.getState().document;
    await useJobStore.getState().submit();
    expect(useJobStore.getState().jobs['project-1'].state).toBe('QUEUED');
    const saved = localStorage.getItem('panelflow-recompute-jobs-v1')!;
    expect(JSON.parse(saved).state).toEqual({tracking: useJobStore.getState().tracking});
    const intent = useJobStore.getState().tracking['project-1'];
    useJobStore.setState({tracking: {}, jobs: {}});
    localStorage.setItem('panelflow-recompute-jobs-v1', saved);
    await useJobStore.persist.rehydrate();
    await useJobStore.getState().refresh('project-1');
    expect(api.fetchRecomputeJob).toHaveBeenCalledWith('project-1', 'job-1', undefined);
    expect(api.submitRecomputeJob).toHaveBeenCalledTimes(1);
    expect(useJobStore.getState().tracking['project-1']).toEqual(intent);
    expect(useProjectStore.getState().document).toBe(original);
  });
  it('reconciles a lost submit acknowledgement using the same persisted key and request', async () => {
    api.submitRecomputeJob.mockRejectedValueOnce(new Error('Connection lost'));
    await useJobStore.getState().submit();
    const intent = useJobStore.getState().tracking['project-1'];
    useProjectStore.setState({editSequence: 5, hasUnsavedChanges: true});
    await useJobStore.getState().refresh('project-1');
    expect(api.submitRecomputeJob.mock.calls[0].slice(0, 3)).toEqual(api.submitRecomputeJob.mock.calls[1].slice(0, 3));
    expect(useJobStore.getState().tracking['project-1'].key).toBe(intent.key);
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
  });
  it('discovers server jobs when browser tracking is absent', async () => {
    api.listRecomputeJobs.mockResolvedValue([complete()]);
    await useJobStore.getState().refresh('project-1');
    expect(useJobStore.getState().tracking['project-1']).toMatchObject({jobId: 'job-1', baseSha256: 'a'.repeat(64)});
    expect(useProjectStore.getState().document?.document.document_sequence).toBe(7);
  });
  it('cancels the durable job and rejects an older running status arriving after cancellation', async () => {
    await useJobStore.getState().submit();
    const response = deferred<RecomputeJob>();
    api.fetchRecomputeJob.mockReturnValue(response.promise);
    const poll = useJobStore.getState().refresh('project-1');
    api.cancelRecomputeJob.mockResolvedValue(job('CANCELLED'));
    await useJobStore.getState().cancel('project-1');
    response.resolve(job('RUNNING')); await poll;
    expect(useJobStore.getState().jobs['project-1'].state).toBe('CANCELLED');
    expect(useProjectStore.getState().document).toEqual(view());
  });
  it('shows stage failure and creates a fresh retry key against the current saved base', async () => {
    await useJobStore.getState().submit();
    const key = useJobStore.getState().tracking['project-1'].key;
    api.fetchRecomputeJob.mockResolvedValue({...job('FAILED'), error: {code: 'ROUTING_INFEASIBLE', message: 'Failed'},
      result: {current_stage: null, stage_executions: [{stage_id: 'routes', adapter: 'routes', status: 'FAILED',
        failure_code: 'ROUTING_INFEASIBLE', executions: 1, elapsed_ms: 12, input_signature: null}]}});
    await useJobStore.getState().refresh('project-1');
    expect(useJobStore.getState().jobs['project-1'].result?.stage_executions?.[0].failure_code).toBe('ROUTING_INFEASIBLE');
    await useJobStore.getState().submit(true);
    expect(useJobStore.getState().tracking['project-1'].key).not.toBe(key);
    expect(api.submitRecomputeJob).toHaveBeenCalledTimes(2);
  });
  it('never installs a completed proposal automatically; explicit apply uses a retained acceptance key', async () => {
    const original = useProjectStore.getState().document;
    await useJobStore.getState().submit();
    api.fetchRecomputeJob.mockResolvedValue(complete());
    await useJobStore.getState().refresh('project-1');
    expect(useProjectStore.getState().document).toBe(original);
    const next = view(); next.document.document_sequence++;
    api.acceptGenerationProposal.mockRejectedValueOnce(new Error('Lost receipt')).mockResolvedValue({result: next});
    await useJobStore.getState().apply('project-1');
    await useJobStore.getState().apply('project-1');
    expect(api.acceptGenerationProposal.mock.calls[0]).toEqual(api.acceptGenerationProposal.mock.calls[1]);
    expect(useProjectStore.getState().document).toEqual(next);
    expect(useJobStore.getState().tracking['project-1'].applied).toBe(true);
  });
  it.each(['sequence', 'lock', 'hash', 'project', 'inputs', 'transforms', 'recovery', 'history', 'command'])(
    'retains late completion without permitting apply after %s changes', async change => {
      await useJobStore.getState().submit();
      if (change === 'sequence') {const next = view(); next.document.document_sequence++; useProjectStore.setState({document: next});}
      if (change === 'lock') useProjectStore.setState({lockVersion: 4});
      if (change === 'hash') useProjectStore.setState({document: {...view(), content_sha256: 'b'.repeat(64)}});
      if (change === 'project') useProjectStore.setState({projectId: 'other'});
      if (change === 'inputs') useProjectStore.getState().setRequirementValue('incomer_rating', 400);
      if (change === 'transforms') useProjectStore.setState({editorTransforms: {Q1: {x: 1, y: 2, z: 3, rotation_deg: 0}}});
      if (change === 'recovery') useProjectStore.setState({pendingRecovery: {} as any});
      if (change === 'history') useProjectStore.setState({viewedRevisionId: 'historical'});
      if (change === 'command') useCommandStore.setState({pending: true});
      const retained = useProjectStore.getState();
      api.fetchRecomputeJob.mockResolvedValue(complete());
      await useJobStore.getState().refresh('project-1');
      await useJobStore.getState().apply('project-1');
      expect(api.acceptGenerationProposal).not.toHaveBeenCalled();
      expect(useProjectStore.getState()).toBe(retained);
      expect(useJobStore.getState().errors['project-1']).toContain('base changed');
    });
  it('protects edits made while acceptance is in flight', async () => {
    await useJobStore.getState().submit();
    api.fetchRecomputeJob.mockResolvedValue(complete());
    await useJobStore.getState().refresh('project-1');
    const response = deferred<{result: DocumentView}>(); api.acceptGenerationProposal.mockReturnValue(response.promise);
    const apply = useJobStore.getState().apply('project-1');
    useProjectStore.getState().setRequirementValue('incomer_rating', 400);
    const retained = useProjectStore.getState().document;
    response.resolve({result: view()}); await apply;
    expect(useProjectStore.getState().document).toBe(retained);
    expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(400);
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
    expect(useJobStore.getState().errors['project-1']).toContain('Newer editor state retained');
  });
  it('uses non-overlapping polling and aborts transport when the workspace unmounts', async () => {
    vi.useFakeTimers();
    const response = deferred<RecomputeJob[]>(); api.listRecomputeJobs.mockReturnValue(response.promise);
    const stop = pollDocumentJobs('project-1');
    await vi.advanceTimersByTimeAsync(5000);
    expect(api.listRecomputeJobs).toHaveBeenCalledTimes(1);
    const signal = api.listRecomputeJobs.mock.calls[0][1] as AbortSignal;
    stop(); response.resolve([]); await vi.advanceTimersByTimeAsync(5000);
    expect(signal.aborted).toBe(true);
    expect(api.listRecomputeJobs).toHaveBeenCalledTimes(1);
  });
  it('keeps acceptance conflicts visible across successful background polls', async () => {
    await useJobStore.getState().submit();
    api.fetchRecomputeJob.mockResolvedValue(complete());
    await useJobStore.getState().refresh('project-1');
    useProjectStore.setState({lockVersion: 99});
    await useJobStore.getState().apply('project-1');
    await useJobStore.getState().refresh('project-1');
    expect(useJobStore.getState().errors['project-1']).toContain('base changed');
    expect(useJobStore.getState().statusErrors['project-1']).toBeNull();
  });
});
