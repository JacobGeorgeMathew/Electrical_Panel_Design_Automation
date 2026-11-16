import {test, expect, openHarness, readDocument, pickComponent, expectAuthoritativeXMove} from './fixtures';

test('acceptance oracle rejects mesh-only movement with unchanged saved PDM', async ({page, projectId}) => {
  await openHarness(page, projectId);
  await pickComponent(page, 'QF001');
  await page.getByTitle('Move selected component', {exact: true}).click();
  await expect.poll(() => page.evaluate(() => window.panelE2E.gizmoPoint()?.axis)).toBe('X');
  const before = await readDocument(page);
  const x = await page.evaluate(() => window.panelE2E.renderedX());
  const writes: string[] = [];
  page.on('request', request => {if (request.method() !== 'GET') writes.push(request.url());});
  await page.evaluate(() => window.panelE2E.shiftMeshOnly(25));
  const renderedX = await page.evaluate(() => window.panelE2E.renderedX());
  expect(renderedX).toBeCloseTo(x + 25, 5);
  const response = await page.request.get(`/api/v1/projects/${projectId}/document`);
  expect(response.status()).toBe(200);
  const saved = await response.json();
  expect(saved).toEqual(before);
  expect(await readDocument(page)).toEqual(before);
  expect(writes).toEqual([]);
  // The same oracle is exercised by the positive production gizmo test.
  expect(() => expectAuthoritativeXMove(before, saved, renderedX)).toThrow('Saved PDM must move');
  const history = await page.request.get(`/api/v1/projects/${projectId}/document/operations/history`);
  expect((await history.json()).undo_batch_ids).toEqual([]);
  await page.reload();
  await expect.poll(async () => (await readDocument(page))?.content_sha256).toBe(before.content_sha256);
  await expect(page.getByRole('region', {name: '3D panel canvas'}).locator('canvas')).toBeVisible();
  await pickComponent(page, 'QF001');
  await page.getByTitle('Move selected component', {exact: true}).click();
  await expect.poll(() => page.evaluate(() => window.panelE2E.renderedX())).toBeCloseTo(x, 5);
});

test('automatic proposal uses explicit API review, exact acceptance, saved reopen and shared undo', async ({page, request}) => {
  // No automatic proposal UI exists yet. Exercise its actual HTTP boundary and
  // then load the accepted document into the production viewers/history tools.
  const created = await request.post('/api/projects', {data: {name: 'P2 acceptance automatic proposal'}});
  expect(created.status()).toBe(201);
  const {id: projectId} = await created.json();
  const documentPath = `/api/v1/projects/${projectId}/document`;
  const proposalPath = `/api/projects/${projectId}/design/generation-proposal`;
  const before = await (await request.get(documentPath)).json();
  const response = await request.post(proposalPath, {data: {num_feeders: 5}});
  expect(response.status()).toBe(200);
  const proposal = await response.json();
  expect(proposal).toMatchObject({status: 'REVIEW_REQUIRED', persisted: false, conflicts: []});
  expect(proposal.batch.operations).toHaveLength(1);
  expect(proposal.batch.operations[0].type).toBe('ApplyGeneration');
  expect(await (await request.get(documentPath)).json()).toEqual(before);
  expect(await (await request.get(`/api/projects/${projectId}/revisions`)).json()).toEqual([]);
  const headers = {'Idempotency-Key': crypto.randomUUID()};
  const accepted = await request.post(proposalPath + '/accept', {data: proposal.batch, headers});
  expect(accepted.status()).toBe(200);
  const receipt = await accepted.json();
  const retry = await request.post(proposalPath + '/accept', {data: proposal.batch, headers});
  expect(retry.status()).toBe(200);
  expect(await retry.json()).toEqual(receipt);
  const committed = await (await request.get(documentPath)).json();
  expect(committed.snapshots).toEqual(proposal.preview.candidate.snapshots);
  expect(committed.document.document_sequence).toBe(before.document.document_sequence + 1);
  expect(committed.document.dirty_stages).toContain('cad');
  expect(await (await request.get(`/api/projects/${projectId}/revisions`)).json()).toEqual([]);
  const stale = await request.post(proposalPath + '/accept', {
    data: proposal.batch, headers: {'Idempotency-Key': crypto.randomUUID()},
  });
  expect(stale.status()).toBe(409);
  expect(await (await request.get(documentPath)).json()).toEqual(committed);
  await openHarness(page, projectId);
  const saved = page.waitForResponse(r => r.url().endsWith(`/projects/${projectId}`) && r.request().method() === 'PATCH');
  await page.getByRole('button', {name: 'Save draft', exact: true}).click();
  expect((await saved).status()).toBe(200);
  await page.reload();
  await expect.poll(async () => (await readDocument(page))?.content_sha256).toBe(committed.content_sha256);
  await page.getByRole('button', {name: 'Undo operation', exact: true}).click();
  await expect.poll(async () => (await readDocument(page)).snapshots).toEqual(before.snapshots);
  expect(await (await request.get(`/api/projects/${projectId}/revisions`)).json()).toEqual([]);
});
