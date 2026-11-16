import {test, expect, openHarness, readDocument, moveRequest, propose, pickComponent,
  drag, saveAndReopen, stalePeer} from './fixtures';

test('viewport renders WebGL, picks a component, commits a gizmo drag and resizes fullscreen', async ({page, projectId}) => {
  await openHarness(page, projectId);
  const before = await readDocument(page);
  await pickComponent(page, 'QF001');
  const canvas = page.getByRole('region', {name: '3D panel canvas'}).locator('canvas');
  expect(await canvas.evaluate(element => !!((element as HTMLCanvasElement).getContext('webgl2') ||
    (element as HTMLCanvasElement).getContext('webgl')))).toBe(true);
  await page.getByTitle('Move selected component', {exact: true}).click();
  await expect(page.getByTitle('Move selected component', {exact: true})).toHaveAttribute('aria-pressed', 'true');
  // Real TransformControls X axis: gesture release commits one MoveComponent.
  await expect.poll(()=>page.evaluate(()=>window.panelE2E.gizmoPoint()?.axis)).toBe('X');
  const point=await page.evaluate(()=>window.panelE2E.gizmoPoint()!);
  await drag(page, point, {x: point.x + 50, y: point.y});
  await expect.poll(() => page.evaluate(() => window.panelE2E.state().document?.document.document_sequence)).toBe(1);
  const state = await page.evaluate(() => window.panelE2E.state());
  expect(state.document!.snapshots.pdm!.components[0].position.x).not.toBe(before.snapshots.pdm!.components[0].position.x);
  expect(state.document!.snapshots.pdm!.components[0].position.y).toBe(before.snapshots.pdm!.components[0].position.y);
  expect(state.document!.snapshots.pdm!.components[0].position.z).toBe(before.snapshots.pdm!.components[0].position.z);
  expect(state.transforms).toEqual({});
  expect(state.proposal).toBeNull();
  expect(state.document!.snapshots.pdm!.routes).toEqual(before.snapshots.pdm!.routes);
  const saved = await page.request.get(`/api/v1/projects/${projectId}/document`);
  expect(await saved.json()).toEqual(state.document);
  const history=await page.request.get(`/api/v1/projects/${projectId}/document/operations/history`);
  expect((await history.json()).undo_batch_ids).toHaveLength(1);
  await page.getByTitle('Undo transform',{exact:true}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.pdm!.components[0].position).toEqual(before.snapshots.pdm!.components[0].position);
  await page.getByTitle('Redo transform',{exact:true}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.pdm!.components[0].position).toEqual(state.document!.snapshots.pdm!.components[0].position);

  const originalCanvas = await canvas.elementHandle();
  const region = page.getByRole('region', {name: '3D panel canvas'});
  const oldBox = await canvas.boundingBox();
  await page.getByRole('button', {name: 'Fullscreen 3D panel', exact: true}).click();
  await expect(region).toHaveAttribute('data-expanded', 'true');
  await expect.poll(async () => (await canvas.boundingBox())!.width).toBeGreaterThan(oldBox!.width);
  expect(await originalCanvas!.evaluate(element => element === document.querySelector('canvas'))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(region).toHaveAttribute('data-expanded', 'false');
  await expect(page.getByRole('button', {name: 'Fullscreen 3D panel', exact: true})).toBeFocused();
  await page.setViewportSize({width: 1000, height: 800});
  await expect.poll(async () => (await canvas.boundingBox())!.width).toBeGreaterThan(100);
  expect(await originalCanvas!.evaluate(element => element === document.querySelector('canvas'))).toBe(true);
});

test('command client previews without writes, commits, exact-retries and saves/reopens', async ({page, projectId}) => {
  await openHarness(page, projectId);
  const before = await readDocument(page);
  const request = moveRequest(before);
  const proposal = await propose(page, projectId, request);
  await page.evaluate(() => window.panelE2E.preview());
  const preview = await page.evaluate(() => window.panelE2E.state().preview);
  expect(preview).toMatchObject({status: 'PREVIEW', persisted: false});
  expect(preview!.candidate.snapshots.pdm!.components[0].position.x).toBe(140);
  expect(await readDocument(page)).toEqual(before);
  expect(await (await page.request.get(`/api/v1/projects/${projectId}/document`)).json()).toEqual(before);
  const response = page.waitForResponse(r => r.url().endsWith('/operations/commit') && r.request().method() === 'POST');
  await page.evaluate(() => window.panelE2E.commit());
  expect((await response).status()).toBe(200);
  const committed = await readDocument(page);
  expect(committed.document.document_sequence).toBe(before.document.document_sequence + 1);
  expect(committed.document.lock_version).toBe(before.document.lock_version + 1);
  expect(committed.snapshots.pdm!.components[0].position.x).toBe(140);
  expect(committed.snapshots.cem).toEqual(before.snapshots.cem);
  expect(committed.snapshots.pdm!.routes).toEqual(before.snapshots.pdm!.routes);
  // Durable exact retry is tested via HTTP after the client consumed its proposal.
  const retry = await page.request.post(`/api/v1/projects/${projectId}/document/operations/commit`, {
    data: request, headers: {'Idempotency-Key': proposal.key}});
  expect(retry.status()).toBe(200);
  expect(await retry.json()).toEqual(await page.evaluate(() => window.panelE2E.state().receipt));
  await saveAndReopen(page, projectId);
  expect(await readDocument(page)).toEqual(committed);
});

test('stale browser conflict retains its proposal and cannot overwrite the winner', async ({page, projectId}) => {
  await openHarness(page, projectId);
  const peer = await stalePeer(page, projectId);
  try {
    const base = await readDocument(page);
    const losing = await propose(peer.page, projectId, moveRequest(base, 160));
    await propose(page, projectId, moveRequest(base));
    await page.evaluate(() => window.panelE2E.commit());
    const winner = await readDocument(page);
    expect(winner.document.document_sequence).toBe(base.document.document_sequence + 1);
    const response = peer.page.waitForResponse(r => r.url().endsWith('/operations/commit'));
    await peer.page.evaluate(() => window.panelE2E.commit());
    expect((await response).status()).toBe(409);
    const stale = await peer.page.evaluate(() => window.panelE2E.state());
    expect(stale.error?.status).toBe(409);
    expect(stale.error?.code).toBeTruthy();
    expect(stale.proposal).toEqual(losing);
    expect(stale.document).toEqual(base);
    await page.reload();
    await expect.poll(() => page.evaluate(() => window.panelE2E?.state().document?.content_sha256)).toBe(winner.content_sha256);
  } finally {await peer.close();}
});
