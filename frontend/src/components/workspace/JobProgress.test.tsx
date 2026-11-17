import React, {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {beforeEach, afterEach, expect, it, vi} from 'vitest';
import {JobProgress} from './JobProgress';
import {useJobStore} from '../../stores/jobStore';
import {useProjectStore} from '../../stores/projectStore';
import {useCommandStore} from '../../stores/commandStore';
import {documentFields} from '../../stores/documentStore';
import fixture from '../../types/fixtures/document-v1.json';
import type {DocumentView} from '../../types/document';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  useCommandStore.getState().clear();
  useProjectStore.setState({...documentFields({...fixture, content_sha256: 'a'.repeat(64)} as DocumentView),
    projectId: 'P', isLoadingProject: false, isSaving: false, isGenerating: false,
    hasUnsavedChanges: false, pendingRecovery: null, viewedRevisionId: null});
  useJobStore.setState({tracking: {}, jobs: {P: {id: 'job', document_id: 'document-1',
    base_sequence: 7, base_version: 3, base_sha256: 'a'.repeat(64), state: 'RUNNING',
    attempts: 1, max_attempts: 3, created_at: '', updated_at: '', error: null,
    result: {current_stage: 'routes', stage_executions: []}}}, errors: {}, statusErrors: {}, pending: {}});
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
});
afterEach(() => {act(() => root.unmount()); host.remove(); vi.restoreAllMocks();});
it('shows actual stage progress and durable cancellation controls', () => {
  const cancel = vi.spyOn(useJobStore.getState(), 'cancel').mockResolvedValue();
  act(() => root.render(<JobProgress/>));
  expect(host.textContent).toContain('Duct routing');
  expect(host.textContent).toContain('base sequence 7');
  const button = Array.from(host.querySelectorAll('button')).find(b => b.textContent === 'Cancel job')!;
  act(() => button.click());
  expect(cancel).toHaveBeenCalledWith('P');
});
it('renders structured stage failure and explicit retry', () => {
  const retry = vi.spyOn(useJobStore.getState(), 'submit').mockResolvedValue();
  const job = useJobStore.getState().jobs.P;
  useJobStore.setState({jobs: {P: {...job, state: 'FAILED', error: {code: 'ROUTING_INFEASIBLE', message: 'Duct obstructed'},
    result: {current_stage: null, stage_executions: [{stage_id: 'routes', adapter: 'routes', status: 'FAILED',
      executions: 1, elapsed_ms: 15, input_signature: null, failure_code: 'ROUTING_INFEASIBLE'}]}}}});
  act(() => root.render(<JobProgress/>));
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('ROUTING_INFEASIBLE');
  expect(host.textContent).toContain('Duct routing (routes): FAILED');
  const button = Array.from(host.querySelectorAll('button')).find(b => b.textContent === 'Retry recompute from saved base')!;
  act(() => button.click()); expect(retry).toHaveBeenCalledWith(true);
});
