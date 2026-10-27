import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
vi.mock('@react-three/fiber',()=>({Canvas:()=>null}));
import {CatalogBrowser} from './CatalogBrowser';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);vi.useFakeTimers();});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals();});

it('loads pages from the API and sends category filters',async()=>{
  const mock=vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('/catalog/filters')?
    {categories:['MCB','MCCB'],manufacturers:[]}:{items:[{id:'c1',name:'Catalog breaker',code:'B1',category:'MCB',current_rating:16,width:18,height:80,depth:70}],total:1,page:1,page_size:12})));
  vi.stubGlobal('fetch',mock);
  await act(async()=>{root.render(<CatalogBrowser/>);});
  await act(async()=>{await vi.advanceTimersByTimeAsync(300);});
  expect(host.textContent).toContain('Catalog breaker');
  const select=host.querySelector('[aria-label="Catalog category"]') as HTMLSelectElement;
  await act(async()=>{select.value='MCB';select.dispatchEvent(new Event('change',{bubbles:true}));});
  await act(async()=>{await vi.advanceTimersByTimeAsync(300);});
  expect(mock.mock.calls.some(([url])=>String(url).includes('category=MCB'))).toBe(true);
});
