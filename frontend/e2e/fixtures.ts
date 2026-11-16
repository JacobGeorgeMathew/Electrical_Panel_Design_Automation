import {test as base, expect, type Page} from '@playwright/test';
import type {CommandProposal} from '../src/stores/commandStore';
import type {DocumentView} from '../src/types/document';
import type {OperationPreviewRequest} from '../src/types/operations';
import type {} from './harness';

export const test = base.extend<{projectId: string}>({
  page: async ({page}, use) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await use(page);
    expect(errors, 'Uncaught browser errors').toEqual([]);
  },
  baseURL: async ({}, use) => {
    if (!process.env.PANEL_E2E_BASE_URL) throw new Error('Run with playwright.config.ts (isolated setup required).');
    await use(process.env.PANEL_E2E_BASE_URL);
  },
  projectId: async ({request}, use) => {
    const response = await request.post('/__e2e__/projects');
    expect(response.ok()).toBeTruthy();
    const {projectId} = await response.json();
    const document = await request.get(`/api/v1/projects/${projectId}/document`);
    expect(document.ok()).toBeTruthy();
    expect((await document.json()).document).toMatchObject({document_sequence: 0, lock_version: 1});
    await use(projectId);
    // All projects/assets disappear with the run-owned DB/temp directory.
  },
});
export {expect};

export async function openHarness(page: Page, projectId: string) {
  await page.goto(`/e2e/harness.html?project=${encodeURIComponent(projectId)}`);
  await expect(page.getByRole('region', {name: '3D panel canvas'}).locator('canvas')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.panelE2E.state().document?.document.project_id)).toBe(projectId);
}

export async function readDocument(page: Page) {
  return (await page.evaluate(() => window.panelE2E.state())).document!;
}

/** A visible displacement counts only when the independently fetched PDM moved. */
export function expectAuthoritativeXMove(before: DocumentView, saved: DocumentView, renderedX: number) {
  const original = before.snapshots.pdm!.components[0];
  const component = saved.snapshots.pdm!.components.find(c => c.id === original.id)!;
  expect(component.position.x, 'Saved PDM must move; a mesh-only displacement is not an engineering edit')
    .not.toBe(original.position.x);
  expect(component.position.x).toBeCloseTo(renderedX, 5);
  expect(saved.document.document_sequence).toBeGreaterThan(before.document.document_sequence);
}

export function moveRequest(view: DocumentView, x = 140): OperationPreviewRequest {
  const component = view.snapshots.pdm!.components[0];
  return {schema_version: '1.0.0', batch_id: crypto.randomUUID(),
    document_id: view.document.document_id, base_sequence: view.document.document_sequence,
    expected_version: view.document.lock_version, base_revision_id: view.document.base_revision_id,
    operations: [{operation_id: crypto.randomUUID(), type: 'MoveComponent',
      origin: {kind: 'MANUAL', actor_id: 'browser-harness'},
      preconditions: {snapshot_sha256: view.document.models.pdm!.sha256},
      target: {cem_component_id: component.cem_component_id, pdm_component_id: component.id},
      parameters: {position_mm: {...component.position, x}}}]};
}

export async function propose(page: Page, projectId: string, request: OperationPreviewRequest) {
  const proposal: CommandProposal = {kind: 'operations', projectId, key: crypto.randomUUID(), request};
  await page.evaluate(value => window.panelE2E.propose(value), proposal);
  return proposal;
}

export async function pickComponent(page: Page, id: string) {
  let point = {x: 0, y: 0};
  // Hover/poll waits for the live scene, fonts and camera to become pickable.
  await expect(async () => {
    point = await page.evaluate(value => window.panelE2E.point(value), id);
    await page.mouse.click(point.x, point.y + 3);
    await expect(page.getByRole('status', {name: 'Harness selection'})).toHaveText(id, {timeout: 1000});
  }).toPass();
  return point;
}

export async function drag(page: Page, from: {x: number; y: number}, to: {x: number; y: number}) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  try {await page.mouse.move(to.x, to.y, {steps: 12});}
  finally {await page.mouse.up();}
}

export async function saveAndReopen(page: Page, projectId: string) {
  const saved = await page.evaluate(() => window.panelE2E.save());
  await page.reload();
  await expect.poll(() => page.evaluate(() => window.panelE2E?.state().document?.content_sha256)).toBe(saved.content_sha256);
  expect((await readDocument(page)).document.project_id).toBe(projectId);
  return saved;
}

/** Another real browser context holds a stale independent document/store. */
export async function stalePeer(page: Page, projectId: string) {
  const context = await page.context().browser()!.newContext({baseURL: process.env.PANEL_E2E_BASE_URL});
  const peer = await context.newPage();
  try {await openHarness(peer, projectId);}
  catch (error) {await context.close(); throw error;}
  return {page: peer, close: () => context.close()};
}
