import { API_BASE } from './config';
import type { PhysicalDesignModel } from '../types/pdm';
import type { ProjectRecord, ProjectConfiguration, DesignPackage, RevisionSummary, Question, Archetype, CatalogPage, CatalogComponent, Enclosure, Artifact } from '../types/api';

export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = 'NETWORK_ERROR') { super(message); }
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
      throw new ApiError(message + (errors?.length ? ' ' + errors.join(' ') : ''), response.status, detail?.code || 'API_ERROR');
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
export const assetUrl = (path: string) => new URL(path, API_BASE).toString();
export const listProjects = (signal?: AbortSignal) => request<ProjectRecord[]>('/projects?page_size=100', { signal });
export const fetchArchetypes = () => request<Archetype[]>('/archetypes');
export const fetchArchetype = (code: string, signal?: AbortSignal) => request<{ questions: Question[] }>('/archetypes/' + id(code) + '/questionnaire', { signal });
export const createProject = (name: string, requirements: Record<string, any>, archetype = 'DB', archetypeVersionId?: string) =>
  request<ProjectRecord>('/projects', json('POST', { name, archetype, archetype_version_id: archetypeVersionId, requirements }));
export const fetchProject = (projectId: string, signal?: AbortSignal) => request<ProjectRecord>('/projects/' + id(projectId), { signal });
export const updateProject = (projectId: string, version: number, values: { name?: string; requirements?: Record<string, any>; configuration?: ProjectConfiguration }) =>
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
  request<{ new_design: DesignPackage; diff_report: any }>('/projects/' + id(projectId) + '/design/propagate-change',
    json('POST', { modified_field: modifiedField, new_value: newValue, expected_version: version }), 90000);
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
