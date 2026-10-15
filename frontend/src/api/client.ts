import { API_BASE } from "./config";
import type { PhysicalDesignModel } from "../types/pdm";

async function readResponse(res: Response) {
  if (res.ok) return res.json();
  let detail: any;
  try { detail = await res.json(); } catch { detail = null; }
  const message = detail?.error?.message || detail?.detail?.message || detail?.detail || detail?.message || `Request failed (${res.status})`;
  const errors = detail?.error?.errors || detail?.error?.details?.validation_errors;
  throw new Error(Array.isArray(errors) && errors.length ? `${message} ${errors.join(" ")}` : String(message));
}

export async function createProject(name: string, requirements: Record<string, any>) {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, archetype: 'DB', requirements }),
  });
  return readResponse(res);
}

export async function validateRequirements(projectId: string, values: Record<string, any>) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/requirements/validate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
  });
  return readResponse(res);
}

export async function fetchProject(projectId: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}`);
  return readResponse(res);
}

export async function fetchQuestionnaire(projectId: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/requirements/questions`);
  return readResponse(res);
}

export async function generateDesign(projectId: string, overrides?: Record<string, any>) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/design/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overrides || {}),
  });
  return readResponse(res);
}

export async function propagateChange(projectId: string, modifiedField: string, newValue: any) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/design/propagate-change`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ modified_field: modifiedField, new_value: newValue }),
  });
  return readResponse(res);
}

export async function fetchFreeCADScript(projectId: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/cad/freecad-script`);
  return readResponse(res);
}

export async function validatePlacement(projectId: string, pdm: PhysicalDesignModel) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/design/validate-placement`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pdm),
  });
  return readResponse(res);
}
