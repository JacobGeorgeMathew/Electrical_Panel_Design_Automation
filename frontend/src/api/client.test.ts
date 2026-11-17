import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {request,ApiError,fetchDocument,saveDocument,fetchRevision} from './client';
import {forgetLocalSession} from './localSession';
beforeEach(()=>forgetLocalSession());
afterEach(()=>{vi.unstubAllGlobals();vi.unstubAllEnvs();vi.resetModules();});

describe('API failures and cancellation',()=>{
  it('resolves managed catalog assets with a relative API base',async()=>{
    vi.stubEnv('VITE_API_BASE','/api');vi.resetModules();
    const {assetUrl}=await import('./client');
    expect(assetUrl('/api/assets/catalog.glb')).toBe(window.location.origin+'/api/assets/catalog.glb');
  });
  it('uses the versioned document Save route and explicit historical revision route',async()=>{
    const fetch=vi.fn(async(url:string,_options?:RequestInit)=>new Response(
      url.endsWith('/local-session') ? JSON.stringify({token:'a'.repeat(64)}) : '{}',{status:200}));vi.stubGlobal('fetch',fetch);
    await fetchDocument('P/1');
    expect(fetch.mock.calls[0][0]).toContain('/api/v1/projects/P%2F1/document');
    await saveDocument('P/1',{document_id:'D',expected_version:4,expected_document_sequence:7,
      requirements:{project_id:'P',archetype:'DB',items:[],is_valid:false,validation_errors:[],validation_warnings:[]}});
    expect(fetch.mock.calls[2][1]).toMatchObject({method:'PUT'});
    expect(new Headers(fetch.mock.calls[2][1]?.headers).get('X-Panel-Session')).toBe('a'.repeat(64));
    expect(JSON.parse((fetch.mock.calls[2][1] as RequestInit).body as string)).toMatchObject({expected_version:4,expected_document_sequence:7});
    await fetchRevision('P/1','R/2');
    expect(fetch.mock.calls[3][0]).toContain('/projects/P%2F1/revisions/R%2F2');
  });
  it('normalizes safe database and revision conflict responses',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({error:{code:'REVISION_CONFLICT',message:'Reopen the project.'}}),{status:409})));
    await expect(request('/projects/p')).rejects.toMatchObject({status:409,code:'REVISION_CONFLICT',message:'Reopen the project.'});
  });
  it('reports unavailable backend without discarding local edits',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>{throw new TypeError('network');}));
    await expect(request('/projects')).rejects.toThrow('local edits have been retained');
  });
  it('aborts a timed-out request',async()=>{
    vi.stubGlobal('fetch',vi.fn((_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))))));
    await expect(request('/projects',{},10)).rejects.toMatchObject({code:'ABORTED'});
  });
});
