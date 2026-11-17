import { API_BASE } from './config';
import type { DocumentSave, DocumentView } from '../types/document';
import type { PhysicalDesignModel } from '../types/pdm';
import type { ProjectRecord, ProjectConfiguration, DesignPackage, RevisionSummary, Question, Archetype, CatalogPage, CatalogComponent, Enclosure, Artifact } from '../types/api';

export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = 'NETWORK_ERROR', public details: unknown = null) { super(message); }
}

export async function request<T>(path: string, options: RequestInit = {}, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, timeoutMs);
  try {
    const response = await fetch(API_BASE.replace(/\/$/, '') + path, { ...options, signal: controller.signal,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.error || data?.detail;
      const errors = detail?.errors || detail?.details?.validation_errors;
      const message = Array.isArray(detail) ? detail.map((e: any) => e.msg).join(' ') :
        detail?.message || (typeof detail === 'string' ? detail : data?.message) || 'Request failed (' + response.status + ')';
      throw new ApiError(message + (errors?.length ? ' ' + errors.join(' ') : ''), response.status, detail?.code || 'API_ERROR', detail);
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) throw new ApiError(options.signal?.aborted ? 'Request cancelled.' : 'Request timed out. Reopen the project to check whether the save completed.', 0, 'ABORTED');
    throw new ApiError('The design API is unavailable. Your local edits have been retained.');
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });
const id = encodeURIComponent;
const operationPath = (projectId: string) => '/v1/projects/' + id(projectId) + '/document/operations';
export const fetchOperationHistory = (projectId: string, signal?: AbortSignal) =>
  request<import('../types/operations').OperationHistory>(operationPath(projectId) + '/history', {signal});
export const previewOperations = (projectId: string, data: import('../types/operations').OperationPreviewRequest, signal?: AbortSignal) =>
  request<import('../types/operations').OperationPreview>(operationPath(projectId) + '/preview', {...json('POST', data), signal});
export const commitOperations = (projectId: string, data: import('../types/operations').OperationPreviewRequest, key: string, signal?: AbortSignal) =>
  request<import('../types/operations').OperationCommit>(operationPath(projectId) + '/commit', {...json('POST', data), headers: {'Idempotency-Key': key}, signal}, 90000);
export const applyOperationHistory = (projectId: string, data: import('../types/operations').HistoryRequest, key: string, signal?: AbortSignal) =>
  request<import('../types/operations').OperationCommit>(operationPath(projectId) + '/history', {...json('POST', data), headers: {'Idempotency-Key': key}, signal}, 90000);
export const proposeGeneration = (projectId: string, overrides: Record<string, unknown> = {}, signal?: AbortSignal) =>
  request<import('../types/operations').GenerationProposal>('/projects/' + id(projectId) + '/design/generation-proposal', {...json('POST', overrides), signal}, 90000);
export const acceptGenerationProposal = (projectId: string, batch: import('../types/operations').OperationPreviewRequest, key: string, signal?: AbortSignal) =>
  request<import('../types/operations').OperationCommit>('/projects/' + id(projectId) + '/design/generation-proposal/accept', {...json('POST', batch), headers: {'Idempotency-Key': key}, signal}, 90000);
export const fetchDocument = (projectId: string, signal?: AbortSignal) =>
  request<DocumentView>('/v1/projects/' + id(projectId) + '/document', { signal });
export const saveDocument = (projectId: string, data: DocumentSave) =>
  request<DocumentView>('/v1/projects/' + id(projectId) + '/document', json('PUT', data));
export const fetchRevision = (projectId: string, revisionId: string, signal?: AbortSignal) =>
  request<DesignPackage>('/projects/' + id(projectId) + '/revisions/' + id(revisionId), { signal });
export const fetchRequirementSuggestions=(projectId:string,archetype:string,values:Record<string,unknown>,signal?:AbortSignal)=>
  request<import('../types/api').RequirementSuggestions>(projectId?'/projects/'+id(projectId)+'/requirements/suggestions':'/archetypes/'+id(archetype)+'/suggestions',
    {...json('POST',values),signal});
export const assetUrl = (path: string) => new URL(path, new URL(API_BASE, window.location.href)).toString();
export const listProjects = async (signal?: AbortSignal, q = '', recent = false) => {
  const projects: ProjectRecord[] = [];
  for (let page=1;;page++) {
    const rows=await request<ProjectRecord[]>('/projects?'+new URLSearchParams({page:String(page),page_size:'100',q,recent:String(recent)}),{signal});
    projects.push(...rows);
    if(rows.length<100)return projects;
  }
};
export const fetchArchetypes = () => request<Archetype[]>('/archetypes');
export const fetchArchetype = (code: string, signal?: AbortSignal) => request<{ questions: Question[] }>('/archetypes/' + id(code) + '/questionnaire', { signal });
export const createProject = (name: string, requirements: Record<string, any>, archetype = 'DB', archetypeVersionId?: string, metadata: {description?:string;location?:string} = {}) =>
  request<ProjectRecord>('/projects', json('POST', { name, archetype, archetype_version_id: archetypeVersionId, requirements, ...metadata }));
export const fetchProject = (projectId: string, signal?: AbortSignal) => request<ProjectRecord>('/projects/' + id(projectId), { signal });
export const updateProject = (projectId: string, version: number, values: { name?: string; requirements?: Record<string, any>; configuration?: ProjectConfiguration; description?:string; location?:string; workspace?:ProjectRecord['workspace']; expected_recovery_version?:number }) =>
  request<ProjectRecord>('/projects/' + id(projectId), json('PATCH', { expected_version: version, ...values }));
export const fetchQuestionnaire = (projectId: string, signal?: AbortSignal) =>
  request<Question[]>('/projects/' + id(projectId) + '/requirements/questions', { signal });
export const validateRequirements = (projectId: string, values: Record<string, any>) =>
  request<{ is_valid: boolean; validation_errors: string[]; validation_warnings: string[] }>('/projects/' + id(projectId) + '/requirements/validate', json('POST', values));
export const generateDesign = (projectId: string, overrides: Record<string, any> = {}, version?: number, configuration?: ProjectConfiguration) =>
  version ? request<DesignPackage>('/projects/' + id(projectId) + '/revisions', json('POST', { requirements: overrides, expected_version: version, configuration }), 90000) :
    request<DesignPackage>('/projects/' + id(projectId) + '/design/generate', json('POST', overrides), 90000);
export const fetchDesign = (projectId: string, signal?: AbortSignal) => request<DesignPackage>('/projects/' + id(projectId) + '/design', { signal });
export const fetchRevisions = (projectId: string) => request<RevisionSummary[]>('/projects/' + id(projectId) + '/revisions');
export const restoreRevision = (projectId: string, revisionId: string, version: number) =>
  request<DesignPackage>('/projects/' + id(projectId) + '/revisions/' + id(revisionId) + '/restore', json('POST', { expected_version: version }));
export const propagateChange = (projectId: string, modifiedField: string, newValue: any, version?: number) =>
  request<{ status: 'PREVIEW'; persisted: false; batch: import('../types/operations').OperationPreviewRequest;
    preview: import('../types/operations').OperationPreview }>('/projects/' + id(projectId) + '/design/propagate-change',
    json('POST', { modified_field: modifiedField, new_value: newValue, expected_version: version }), 90000);
export const recomputeDesign = (projectId: string, data: import('../types/operations').RecomputeRequest) =>
  request<import('../types/operations').RecomputeResponse>('/projects/' + id(projectId) + '/design/recompute',
    json('POST', data), 90000);
const recomputeJobsPath = (projectId: string) => '/projects/' + id(projectId) + '/design/recompute/jobs';
export const submitRecomputeJob = (projectId: string, data: import('../types/jobs').RecomputeJobRequest, key: string, signal?: AbortSignal) =>
  request<import('../types/jobs').RecomputeJob>(recomputeJobsPath(projectId),
    {...json('POST', data), headers: {'Idempotency-Key': key}, signal});
export const listRecomputeJobs = (projectId: string, signal?: AbortSignal) =>
  request<import('../types/jobs').RecomputeJob[]>(recomputeJobsPath(projectId), {signal});
export const fetchRecomputeJob = (projectId: string, jobId: string, signal?: AbortSignal) =>
  request<import('../types/jobs').RecomputeJob>(recomputeJobsPath(projectId) + '/' + id(jobId), {signal});
export const cancelRecomputeJob = (projectId: string, jobId: string, signal?: AbortSignal) =>
  request<import('../types/jobs').RecomputeJob>(recomputeJobsPath(projectId) + '/' + id(jobId) + '/cancel', {...json('POST', {}), signal});
export const fetchFreeCADScript = (projectId: string) => request<{ script: string; revision_id: string }>('/projects/' + id(projectId) + '/cad/freecad-script');
export const validatePlacement = (projectId: string, pdm: PhysicalDesignModel) =>
  request<{ pdm: PhysicalDesignModel; validation_results: any[]; is_valid: boolean }>('/projects/' + id(projectId) + '/design/reroute-placement', json('POST', pdm));
export const searchCatalog = (params: URLSearchParams, signal?: AbortSignal) => request<CatalogPage>('/components?' + params, { signal });
export const fetchCatalogComponent = (key: string, signal?: AbortSignal) => request<CatalogComponent>('/components/' + id(key), { signal });
export const fetchAccessories = (key: string, signal?: AbortSignal) => request<CatalogComponent[]>('/components/' + id(key) + '/accessories', { signal });
export const fetchCatalogFilters = () => request<{ categories: string[]; manufacturers: { id: string; name: string }[] }>('/catalog/filters');
export const fetchEnclosures = () => request<Enclosure[]>('/enclosures');
export const startCadJob = (projectId: string, version: number) =>
  request<{ id: string; status: string; project_revision_id: string }>('/projects/' + id(projectId) + '/cad-generation', json('POST', { expected_version: version, file_format: 'GLB' }));
export const fetchCadJob = (projectId: string, jobId: string) => request<Artifact>('/projects/' + id(projectId) + '/cad-generation/' + id(jobId));

export const markProjectOpened=(projectId:string)=>request<ProjectRecord>('/projects/'+id(projectId)+'/open',json('POST',{}));
export const deleteProject=(projectId:string,version:number)=>request<void>('/projects/'+id(projectId),json('DELETE',{expected_version:version}));
export const duplicateProject=(projectId:string,version:number,name:string)=>request<ProjectRecord>('/projects/'+id(projectId)+'/duplicate',json('POST',{expected_version:version,name}),90000);
export const exportProject=(projectId:string)=>request<unknown>('/projects/'+id(projectId)+'/export',{},90000);
export const importProject=(data:unknown)=>request<ProjectRecord>('/projects/import',json('POST',data),90000);
export const saveRecovery=(projectId:string,version:number,recoveryVersion:number,document:import('../types/recovery').RecoveryDocument|null)=>
  request<ProjectRecord>('/projects/'+id(projectId)+'/recovery',json('PUT',{expected_version:version,expected_recovery_version:recoveryVersion,document}));
