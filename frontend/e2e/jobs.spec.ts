import {test, expect, readDocument} from './fixtures';

test('recompute acknowledges asynchronously, resumes after reload and requires explicit review/apply', async ({page, request}) => {
  test.setTimeout(120_000);
  const created = await request.post('/api/projects', {data: {name: 'Async recompute browser', requirements: {num_feeders: 5}}});
  expect(created.status()).toBe(201);
  const {id: projectId} = await created.json();
  await page.goto(`/e2e/harness.html?project=${projectId}`);
  await page.getByRole('tab', {name: 'Activity & errors', exact: true}).click();
  const before = await readDocument(page);
  const ack = page.waitForResponse(r => r.url().endsWith('/design/recompute/jobs') && r.request().method() === 'POST');
  await page.getByRole('button', {name: 'Recompute saved document', exact: true}).click();
  const acknowledged = await ack;
  expect(acknowledged.status()).toBe(202);
  const queued = await acknowledged.json();
  expect(queued.state).toBe('QUEUED');
  expect(await readDocument(page)).toEqual(before);
  await page.reload();
  await page.getByRole('tab', {name: 'Activity & errors', exact: true}).click();
  await expect.poll(() => page.evaluate(() => window.panelE2E.state().job?.id)).toBe(queued.id);
  await expect(page.getByRole('button', {name: 'Apply recompute proposal', exact: true})).toBeEnabled({timeout: 90_000});
  expect((await readDocument(page)).document.document_sequence).toBe(before.document.document_sequence);
  expect(await (await request.get(`/api/projects/${projectId}/revisions`)).json()).toEqual([]);
  await page.getByText('Review recompute effects', {exact: true}).click();
  await expect(page.getByText('Stage execution records', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Apply recompute proposal', exact: true}).click();
  await expect.poll(async () => (await readDocument(page)).document.document_sequence).toBe(before.document.document_sequence + 1);
  const saved = await readDocument(page);
  expect(saved.document.dirty_stages).toEqual([]);
  expect(saved.snapshots.pdm).not.toBeNull();
  await expect(page.getByRole('region', {name: '3D panel canvas'}).locator('canvas')).toBeVisible();
  expect(await (await request.get(`/api/projects/${projectId}/revisions`)).json()).toEqual([]);
  const part = saved.snapshots.pdm!.components.filter(c => c.rail_id)
    .reduce((right, c) => c.position.x + c.width > right.position.x + right.width ? c : right);
  await page.getByRole('button', {name: 'layout2d', exact: true}).click();
  await page.getByRole('button', {name: `Move ${part.cem_component_id}`, exact: true}).click();
  // A new job from this saved base may finish while physical edits continue.
  await page.getByRole('button', {name: 'Recompute saved document', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Apply recompute proposal', exact: true})).toBeEnabled({timeout: 90_000});
  // Keep the 1 mm physical move exact; the default 5 mm display grid would
  // otherwise snap this input back to the accepted position.
  await page.getByLabel('Inspector snap', {exact: true}).uncheck();
  await page.getByLabel('Inspector x', {exact: true}).fill(String(part.position.x + 1));
  await page.getByLabel('Inspector x', {exact: true}).press('Enter');
  await expect.poll(async () => (await readDocument(page)).document.document_sequence).toBe(saved.document.document_sequence + 1);
  const newer = await readDocument(page);
  await page.getByRole('button', {name: 'Apply recompute proposal', exact: true}).click();
  await expect(page.getByRole('alert').filter({hasText: 'Recompute base changed'})).toBeVisible();
  expect(await readDocument(page)).toEqual(newer);
});

test('durable cancellation and retry are visible in the workspace', async ({page, request}) => {
  test.setTimeout(120_000);
  const created = await request.post('/api/projects', {data: {name: 'Cancel recompute browser', requirements: {num_feeders: 5}}});
  const {id: projectId} = await created.json();
  await page.goto(`/e2e/harness.html?project=${projectId}`);
  await page.getByRole('tab', {name: 'Activity & errors', exact: true}).click();
  const before = await readDocument(page);
  await page.getByRole('button', {name: 'Recompute saved document', exact: true}).click();
  await page.getByRole('button', {name: 'Cancel job', exact: true}).click();
  await expect(page.getByText('Job cancelled. The working document is unchanged.', {exact: true})).toBeVisible();
  const cancelled = await page.evaluate(() => window.panelE2E.state().job!);
  expect(cancelled.state).toBe('CANCELLED');
  await page.reload();
  await page.getByRole('tab', {name: 'Activity & errors', exact: true}).click();
  await expect(page.getByText('Job cancelled. The working document is unchanged.', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Retry recompute from saved base', exact: true}).click();
  await expect.poll(() => page.evaluate(() => window.panelE2E.state().job?.id)).not.toBe(cancelled.id);
  await expect(page.getByRole('button', {name: 'Apply recompute proposal', exact: true})).toBeEnabled({timeout: 90_000});
  expect(await readDocument(page)).toEqual(before);
});
