import {test, expect} from './fixtures';
import {readFileSync} from 'node:fs';
import {PerspectiveCamera, Vector3} from 'three';
import {fitPanelCamera} from '../src/components/threeD/cameraFit';

const cases = JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/design_baselines/cases.json', import.meta.url), 'utf8'));
const summary = (samples: number[]) => {
  const ordered = [...samples].sort((a,b) => a-b);
  return {samples_ms: samples, count: samples.length,
    median_ms: ordered.length ? (ordered[Math.floor((ordered.length-1)/2)]+ordered[Math.floor(ordered.length/2)])/2 : null,
    p95_ms: ordered[Math.ceil(.95*ordered.length)-1], max_ms: ordered[ordered.length-1]};
};

for (const board of cases.feasible) test(`D01 production visible performance ${board.id}`, async ({page, request}, info) => {
  const created = await request.post('/api/projects', {data: {name: `MVP performance ${board.id}`,
    requirements: {...cases.requirements, num_feeders: board.num_feeders}}});
  expect(created.status()).toBe(201);
  const {id} = await created.json();
  const path = `/api/projects/${id}`;
  let initial = await (await request.get(`/api/v1/projects/${id}/document`)).json();
  const fence = (view: typeof initial) => ({document_id: view.document.document_id,
    expected_document_sequence: view.document.document_sequence, expected_version: view.document.lock_version});
  const requirements = await request.post(path+'/requirements/validate', {
    data:{...cases.requirements,num_feeders:board.num_feeders}});
  expect(requirements.ok()).toBeTruthy();
  const inputSave = await request.put(`/api/v1/projects/${id}/document`, {data:{...fence(initial),
    requirements:await requirements.json(),configuration:initial.document.configuration}});
  expect(inputSave.ok()).toBeTruthy();
  initial = await inputSave.json();
  const generationStarted = Date.now();
  const generated = await request.post(path+'/design/recompute', {data: fence(initial)});
  const initialExecutionMs = Date.now()-generationStarted;
  expect(generated.ok()).toBeTruthy();
  const proposal = await generated.json();
  const accepted = await request.post(path+'/design/generation-proposal/accept', {
    data: proposal.batch, headers: {'Idempotency-Key': crypto.randomUUID()}});
  expect(accepted.ok()).toBeTruthy();
  const saved = await (await request.get(`/api/v1/projects/${id}/document`)).json();
  expect(saved.snapshots.pdm.components.length).toBe(board.num_feeders*2+5);
  expect(saved.snapshots.pdm.routes.length).toBe(board.num_feeders*3+8);
  // Test instrumentation observes production events/DOM/fetch. No store bridge,
  // mock API, replacement rendering or production engineering writes are added.
  await page.addInitScript(() => {
    const w = window as any;
    w.mvp = {opens: [], acks: [], drag: [], gaps: [], events: 0, previewChanges: 0, pending: 0, recordDrag: false};
    let previousFrame = 0;
    const frame = (now: number) => {
      if (w.mvp.recordDrag && previousFrame) w.mvp.gaps.push(now-previousFrame);
      previousFrame = now; requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
    document.addEventListener('pointermove', event => {
      if (!w.mvp.recordDrag || !(event.buttons & 1)) return;
      const target = (event.target as Element).closest('[aria-label^="Move "]');
      if (!target) return;
      const before = target.getAttribute('transform'), start = performance.now();
      w.mvp.events++;
      w.mvp.pending++;
      const timeout = setTimeout(() => {
        observer.disconnect(); w.mvp.pending--; w.mvp.drag.push(null);
      }, 1000);
      const observer = new MutationObserver(() => {
        if (target.getAttribute('transform') === before) return;
        observer.disconnect(); clearTimeout(timeout);
        requestAnimationFrame(() => {
          w.mvp.previewChanges++; w.mvp.pending--; w.mvp.drag.push(performance.now()-start);
        });
      });
      observer.observe(target, {attributes:true, attributeFilter:['transform']});
    }, true);
    document.addEventListener('click', event => {
      const button = (event.target as Element).closest('button');
      if (button?.textContent === 'Open') w.mvp.openStart = performance.now();
      if (button?.textContent === 'Recompute saved document') w.mvp.ackStart = performance.now();
    }, true);
    const fetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await fetch(...args);
      const url = String(args[0]);
      if (url.endsWith('/design/recompute/jobs') && args[1]?.method === 'POST') {
        const body = await response.clone().json();
        w.mvp.acks.push({ms: performance.now()-w.mvp.ackStart, id: body.id, status: response.status});
      }
      return response;
    };
  });
  const coldStarted = Date.now();
  await page.goto('/');
  const article = page.locator('article').filter({hasText: `MVP performance ${board.id}`});
  await expect(article.getByRole('button', {name: 'Open', exact: true})).toBeVisible();
  const startupMs = Date.now()-coldStarted;
  const opens: number[] = [];
  let openError: string | null = null;
  const requestsDuringDrag: string[] = [];
  page.on('request', req => {
    if (recordNetwork && req.url().includes('/api/')) requestsDuringDrag.push(req.method()+' '+new URL(req.url()).pathname);
  });
  let recordNetwork = false;
  try {
  for (let i=0; i<31; i++) {
    await article.getByRole('button', {name:'Open',exact:true}).click();
    // Include installing saved snapshots and preparing both initial views.
    await page.locator('[data-view="layout2d"]').click();
    await expect(page.getByRole('button', {name: /^Move /}).first()).toBeVisible();
    await page.locator('[data-view="threeD"]').click();
    const canvas = page.getByRole('region', {name:'3D panel canvas'}).locator('canvas');
    await expect(canvas).toBeVisible();
    await page.getByLabel('Camera orientation', {exact:true}).selectOption('front');
    // A canvas alone does not establish readiness. Real raycasting must select
    // the projected saved device before the open interval ends.
    const part = saved.snapshots.pdm.components[0];
    await expect(async () => {
      const rect = (await canvas.boundingBox())!;
      const pdm = saved.snapshots.pdm;
      const fit = fitPanelCamera({width:pdm.enclosure_width*.01,
        height:pdm.enclosure_height*.01,
        depth:(pdm.enclosure_depth+(pdm.accessories?.length?pdm.enclosure_width*.7:0))*.01},rect.width/rect.height);
      const distance = new Vector3(...fit.position).distanceTo(new Vector3(...fit.center));
      const camera = new PerspectiveCamera(45,rect.width/rect.height,.01,1000);
      camera.position.set(fit.center[0],fit.center[1],fit.center[2]+distance);
      camera.lookAt(...fit.center);camera.updateMatrixWorld();
      const p=part.position;
      const point=new Vector3((p.x+part.width/2)*.01,(p.y+part.height/2)*.01,(p.z+part.depth/2)*.01).project(camera);
      await page.mouse.click(rect.x+(point.x+1)*rect.width/2,rect.y+(1-point.y)*rect.height/2+3);
      await expect(page.locator('.status-selection')).toHaveText('Selected: '+part.cem_component_id,{timeout:1000});
    }).toPass({timeout:20000});
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    opens.push(await page.evaluate(() => performance.now()-(window as any).mvp.openStart));
    if (i<30) {
      await page.getByRole('button', {name:'Project dashboard…',exact:true}).click();
      await expect(article).toBeVisible();
    }
  }
  } catch (error) {
    // Preserve an actual readiness failure, then measure independent job/2D
    // paths. A failed open never becomes a timing pass or disappears as outlier.
    openError = String(error);
  }
  if (process.env.PANEL_MVP_OPEN_ONLY === '1') {
    const data = {board:board.id,browser:page.context().browser()!.version(),viewport:page.viewportSize(),
      document_sha256:saved.content_sha256,startup_to_dashboard_ms:startupMs,
      open:{warmup_ms:opens[0],error:openError,...summary(opens.slice(1))}};
    console.log('MVP_CACHED_OPEN '+JSON.stringify(data));
    await info.attach('cached-open', {body:JSON.stringify(data,null,2),contentType:'application/json'});
    expect(openError).toBeNull();
    expect(opens.slice(1)).toHaveLength(30);
    expect(data.open.p95_ms).toBeLessThan(2000);
    expect((await (await request.get(`/api/v1/projects/${id}/document`)).json()).content_sha256).toBe(saved.content_sha256);
    return;
  }
  // Fixed queue: each new durable submission is cancelled/terminal before the
  // next; execution is measured separately and never accepted into the document.
  await page.getByRole('tab', {name:'Activity & errors',exact:true}).click();
  const jobPanel = page.locator('section[aria-label="Recompute job"]');
  const execution: Array<{id:string; terminal:string; observed_ms:number}> = [];
  for (let i=0; i<31; i++) {
    const response = page.waitForResponse(r => r.url().endsWith('/design/recompute/jobs') && r.request().method()==='POST');
    await jobPanel.getByRole('button', {name:'Recompute saved document',exact:true}).click();
    const receipt = await response;
    expect(receipt.status()).toBe(202);
    const job = await receipt.json(), start = Date.now();
    const durable = await request.get(path+'/design/recompute/jobs/'+job.id);
    expect(durable.ok()).toBeTruthy();
    expect((await durable.json()).id).toBe(job.id);
    await expect(page.getByRole('button', {name:'Cancel job',exact:true})).toBeVisible();
    await page.getByRole('button', {name:'Cancel job',exact:true}).click();
    await expect(page.getByText('Job cancelled. The working document is unchanged.',{exact:true})).toBeVisible();
    execution.push({id:job.id, terminal:'CANCELLED', observed_ms:Date.now()-start});
  }
  const acks = await page.evaluate(() => (window as any).mvp.acks);
  expect(acks).toHaveLength(31);
  expect(new Set(acks.map((a:any)=>a.id)).size).toBe(31);
  await page.locator('[data-view="layout2d"]').click();
  await page.getByRole('button', {name:'Move',exact:true}).click();
  const snap = page.getByRole('button', {name:'Disable snapping',exact:true});
  if (await snap.count()) await snap.click();
  const component = saved.snapshots.pdm.components.filter((c:any)=>c.rail_id)
    .reduce((a:any,b:any)=>a.position.x+a.width>b.position.x+b.width?a:b);
  const target = page.getByRole('button', {name:`Move ${component.cem_component_id}`,exact:true});
  const sessions: unknown[] = [];
  for (let session=0; session<5; session++) {
    const box = (await target.boundingBox())!;
    const x=box.x+box.width/2, y=box.y+box.height/2;
    await page.mouse.move(x,y); await page.mouse.down();
    await page.evaluate(() => {const s=(window as any).mvp;s.drag=[];s.gaps=[];s.events=0;s.previewChanges=0;s.recordDrag=true;});
    recordNetwork = true;
    const started = Date.now();
    let index = 0;
    while (Date.now()-started<30_000) {
      await page.mouse.move(x+Math.sin(++index*.5)*4,y);
      await page.waitForTimeout(40);
    }
    // Cancel the preview after the session so floating-point screen transforms
    // cannot introduce a tiny unintended commit between measurement sessions.
    await page.mouse.move(x,y);
    recordNetwork = false;
    await page.evaluate(() => {(window as any).mvp.recordDrag=false;});
    await expect.poll(() => page.evaluate(() => (window as any).mvp.pending)).toBe(0);
    await target.dispatchEvent('pointercancel');
    await page.mouse.up();
    const data = await page.evaluate(() => {const s=(window as any).mvp;return {samples:s.drag,gaps:s.gaps,events:s.events,changes:s.previewChanges,visibility:document.visibilityState};});
    sessions.push({duration_ms:Date.now()-started,...data});
  }
  const data = {board:board.id, browser:page.context().browser()!.version(), viewport:page.viewportSize(),
    mode:'visible production Chromium; platform default renderer', startup_to_dashboard_ms:startupMs,
    document_sha256:saved.content_sha256, model_hashes:saved.document.models,
    open:{warmup_ms:opens[0],error:openError,...summary(opens.slice(1))},
    acknowledgement:{warmup:acks[0],...summary(acks.slice(1).map((a:any)=>a.ms)),receipts:acks},
    initial_full_recompute_ms:initialExecutionMs,
    queue:'one submitted job at a time; cancel before next; no accepted results',execution,
    drag_sessions:sessions, requests_during_drag:requestsDuringDrag,
    renderer:await page.evaluate(() => {const c=document.createElement('canvas'),g=c.getContext('webgl');if(!g)return null;const d=g.getExtension('WEBGL_debug_renderer_info');return d?g.getParameter(d.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER);})};
  const drags = (sessions as any[]).flatMap(s=>s.samples);
  const dragSummary = summary(drags.filter(x=>typeof x==='number'));
  console.log('MVP_PERFORMANCE '+JSON.stringify({board:board.id,
    open:{count:data.open.count,p95_ms:data.open.p95_ms,error:openError},
    acknowledgement:{count:data.acknowledgement.count,p95_ms:data.acknowledgement.p95_ms},
    drag:{count:drags.length,missing:drags.length-dragSummary.count,p95_ms:dragSummary.p95_ms},
    renderer:data.renderer}));
  await info.attach('performance', {body:JSON.stringify(data,null,2),contentType:'application/json'});
  expect((await (await request.get(`/api/v1/projects/${id}/document`)).json()).content_sha256).toBe(saved.content_sha256);
  // Evaluate every budget even when one fails; all failures still fail this test.
  expect.soft(openError).toBeNull();
  expect.soft(opens.slice(1)).toHaveLength(30);
  expect.soft(data.open.p95_ms).toBeLessThan(2000);
  expect.soft(data.acknowledgement.p95_ms).toBeLessThan(500);
  expect(drags.length).toBeGreaterThanOrEqual(200);
  expect(drags.every(x=>typeof x==='number')).toBe(true);
  expect((sessions as any[]).every(s=>s.visibility==='visible' && s.duration_ms>=30000)).toBe(true);
  expect(summary(drags).p95_ms).toBeLessThanOrEqual(33);
  expect(requestsDuringDrag.filter(r=>!r.startsWith('GET '))).toEqual([]);
});
