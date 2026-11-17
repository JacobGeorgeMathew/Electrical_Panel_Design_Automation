import type {RecomputeRequest, RecomputeResponse} from './operations';

export type JobState = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
export type RecomputeJobRequest = RecomputeRequest;
export interface RecomputeJob {
  id: string;
  document_id: string;
  base_sequence: number;
  base_version: number;
  base_sha256: string;
  state: JobState;
  attempts: number;
  max_attempts: number;
  result: {
    current_stage?: string | null;
    stage_executions?: RecomputeResponse['stage_executions'];
    response?: RecomputeResponse;
  } | null;
  error: {code: string; message: string} | null;
  created_at: string;
  updated_at: string;
}
