import { API_BASE } from "./config";

export async function fetchProject(projectId: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}`);
  if (!res.ok) throw new Error('Failed to fetch project');
  return res.json();
}

export async function fetchQuestionnaire(projectId: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/requirements/questions`);
  if (!res.ok) throw new Error('Failed to fetch questionnaire');
  return res.json();
}

export async function validateRequirements(projectId: string, values: Record<string, any>) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/requirements/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!res.ok) throw new Error('Failed to validate requirements');
  return res.json();
}

export async function generateDesign(projectId: string, overrides?: Record<string, any>) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/design/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overrides || {}),
  });
  if (!res.ok) throw new Error('Failed to generate engineering design');
  return res.json();
}

export async function propagateChange(projectId: string, modifiedField: string, newValue: any) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/design/propagate-change`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ modified_field: modifiedField, new_value: newValue }),
  });
  if (!res.ok) throw new Error('Failed to propagate design changes');
  return res.json();
}

export async function fetchFreeCADScript(projectId: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/cad/freecad-script`);
  if (!res.ok) throw new Error('Failed to fetch FreeCAD script');
  return res.json();
}
