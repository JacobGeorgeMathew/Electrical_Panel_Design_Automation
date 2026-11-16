import {test,expect,openHarness,readDocument,drag} from './fixtures';

test('symbol gesture commits presentation only; undo/redo and reopen retain page layout and net hashes',async({page,projectId})=>{
  await openHarness(page,projectId);
  const before=await readDocument(page);
  await page.getByRole('button',{name:'schematic',exact:true}).click();
  const node=page.locator('.react-flow__node[data-id="symbol-1"]');
  await expect(node).toBeVisible();
  await node.hover();
  const box=(await node.boundingBox())!;
  await drag(page,{x:box.x+box.width/2,y:box.y+box.height/2},{x:box.x+box.width/2+80,y:box.y+box.height/2+40});
  await expect.poll(async()=> (await readDocument(page)).document.document_sequence).toBe(1);
  const moved=await readDocument(page);
  expect(moved.document.models.cem).toEqual(before.document.models.cem);
  expect(moved.snapshots.schematic!.symbols[0].position).not.toEqual(before.snapshots.schematic!.symbols[0].position);
  expect(moved.snapshots.pdm).toEqual(before.snapshots.pdm);
  await page.getByRole('button',{name:'Undo operation',exact:true}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.schematic).toEqual(before.snapshots.schematic);
  expect((await readDocument(page)).document.models.cem).toEqual(before.document.models.cem);
  await page.getByRole('button',{name:'Redo operation',exact:true}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.schematic).toEqual(moved.snapshots.schematic);
  const saved=page.waitForResponse(r=>r.url().endsWith(`/projects/${projectId}`)&&r.request().method()==='PATCH');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();expect((await saved).status()).toBe(200);
  await page.reload();
  await expect.poll(async()=> (await readDocument(page)).snapshots.schematic).toEqual(moved.snapshots.schematic);
  expect((await readDocument(page)).document.models.cem).toEqual(before.document.models.cem);
  await page.getByRole('button',{name:'schematic',exact:true}).click();
  const reopened=page.locator('.react-flow__node[data-id="symbol-1"]');
  await expect(reopened).toBeVisible();
  const placement=await reopened.evaluate(e=>{const m=new DOMMatrixReadOnly((e as HTMLElement).style.transform);return {x:m.m41,y:m.m42};});
  expect(placement.x).toBeCloseTo(moved.snapshots.schematic!.symbols[0].position.x,3);
  expect(placement.y).toBeCloseTo(moved.snapshots.schematic!.symbols[0].position.y,3);
});

test('connection replace/delete previews list exact invalidated routes and emptied nets',async({page,request})=>{
  const seeded=await request.post('/__e2e__/projects?electrical=true');expect(seeded.ok()).toBe(true);
  const {projectId}=await seeded.json();await openHarness(page,projectId);
  const base=await readDocument(page);
  await page.getByRole('button',{name:'schematic',exact:true}).click();
  const selectWire=async()=>{
    // A vertical SVG path has a zero-width DOM box. Pick the stroked path
    // away from its middle label; locator.click's box visibility cannot do this.
    await expect(async()=>{
      const point=await page.locator('.react-flow__edge[data-id="wire-1"] .react-flow__edge-path').evaluate(e=>{
        const path=e as SVGPathElement,p=path.getPointAtLength(path.getTotalLength()*.25);
        const point=new DOMPoint(p.x,p.y).matrixTransform(path.getScreenCTM()!);return {x:point.x,y:point.y};
      });
      await page.mouse.click(point.x,point.y);
      await expect(page.getByRole('button',{name:'Edit connection',exact:true})).toBeVisible({timeout:1000});
    }).toPass({timeout:5000});
  };
  await selectWire();
  await page.getByRole('button',{name:'Edit connection',exact:true}).click();
  await page.getByLabel('Conductor area mm2').fill('2.5');await page.getByLabel('Conductor diameter mm').fill('4');
  await page.getByLabel('Conductor insulation').fill('PVC');await page.getByLabel('Conductor bend radius mm').fill('12');
  await page.getByRole('button',{name:'Preview electrical effect'}).click();
  await expect(page.getByLabel('Connection effect preview')).toContainText('Invalidated routes: route-1');
  expect(await readDocument(page)).toEqual(base);
  await page.getByRole('button',{name:'Apply electrical change'}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.pdm!.routes).toEqual([]);
  const replaced=await readDocument(page);
  expect(replaced.snapshots.cem!.connections[0]).toMatchObject({id:'N-PE-C01',cross_section_mm2:2.5});
  await selectWire();
  await page.getByRole('button',{name:'Delete selected wire'}).click();
  await page.getByRole('button',{name:'Preview electrical effect'}).click();
  await expect(page.getByLabel('Connection effect preview')).toContainText('Removed nets: N-PE');
  expect(await readDocument(page)).toEqual(replaced);
  await page.getByRole('button',{name:'Apply electrical change'}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.cem!.connections).toEqual([]);
  expect((await readDocument(page)).snapshots.cem!.nets).toEqual([]);
  await page.getByRole('button',{name:'Undo operation',exact:true}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots).toEqual(replaced.snapshots);
});

test('real pin drag previews electrical effects, valid connection commits; invalid and cancelled edits write nothing',async({page,request})=>{
  const seeded=await request.post('/__e2e__/projects?electrical=true');expect(seeded.ok()).toBe(true);
  const {projectId}=await seeded.json();
  await openHarness(page,projectId);
  const base=await readDocument(page);
  await page.getByRole('button',{name:'schematic',exact:true}).click();
  const from=page.locator('.react-flow__handle.source[data-handleid="source:pin-1"]');
  const to=page.locator('.react-flow__handle.target[data-handleid="target:pin-3"]');
  await expect(from).toBeVisible();await expect(to).toBeVisible();
  await from.hover();
  const a=(await from.boundingBox())!,b=(await to.boundingBox())!;
  await drag(page,{x:a.x+a.width/2,y:a.y+a.height/2},{x:b.x+b.width/2,y:b.y+b.height/2});
  const form=page.getByRole('region',{name:'Connection effect preview'});
  await expect(page.getByLabel('From pin')).toHaveValue('pin-1');
  await expect(page.getByLabel('To pin')).toHaveValue('pin-3');
  await page.getByLabel('Connection net').selectOption('N-PE');
  await page.getByLabel('Conductor area mm2').fill('2.5');
  await page.getByLabel('Conductor diameter mm').fill('4');
  await page.getByLabel('Conductor insulation').fill('PVC');
  await page.getByLabel('Conductor bend radius mm').fill('12');
  await expect(page.getByRole('button',{name:'Apply electrical change'})).toBeDisabled();
  await page.getByRole('button',{name:'Preview electrical effect'}).click();
  await expect(page.getByText(/Server preview accepted/)).toBeVisible();
  expect(await readDocument(page)).toEqual(base);
  const durable=await page.request.get(`/api/v1/projects/${projectId}/document`);expect(await durable.json()).toEqual(base);
  await page.getByRole('button',{name:'Apply electrical change'}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.cem!.connections.length).toBe(2);
  const connected=await readDocument(page);
  expect(connected.snapshots.cem!.connections[1]).toMatchObject({from_component:'QF001',from_terminal:'OUT',to_component:'PE002',to_terminal:'MAIN_PE',net_id:'N-PE'});
  // Duplicate endpoints are invalid. The server must reject the preview atomically.
  await page.getByRole('button',{name:'Connect terminals',exact:true}).click();
  await page.getByLabel('From pin').selectOption('pin-1');await page.getByLabel('To pin').selectOption('pin-3');
  await page.getByLabel('Connection net').selectOption('N-PE');
  await page.getByLabel('Conductor area mm2').fill('2.5');await page.getByLabel('Conductor diameter mm').fill('4');
  await page.getByLabel('Conductor insulation').fill('PVC');await page.getByLabel('Conductor bend radius mm').fill('12');
  await page.getByRole('button',{name:'Preview electrical effect'}).click();
  await expect.poll(()=>page.evaluate(()=>window.panelE2E.state().error?.code)).toBe('OPERATION_CONNECTION');
  expect(await readDocument(page)).toEqual(connected);
  expect(await(await page.request.get(`/api/v1/projects/${projectId}/document`)).json()).toEqual(connected);
  await page.getByRole('button',{name:'Cancel connection edit'}).click();
  await page.getByRole('button',{name:'Undo operation',exact:true}).click();
  await expect.poll(async()=> (await readDocument(page)).snapshots.cem).toEqual(base.snapshots.cem);
});
