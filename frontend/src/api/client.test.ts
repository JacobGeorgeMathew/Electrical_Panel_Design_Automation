import {afterEach,describe,expect,it,vi} from 'vitest';
import {request,ApiError,fetchDocument,saveDocument,fetchRevision} from './client';
afterEach(()=>{vi.unstubAllGlobals();});

describe('API failures and cancellation',()=>{
  it('uses the versioned document Save route and explicit historical revision route',async()=>{
    const fetch=vi.fn(async(_url:string,_options?:RequestInit)=>new Response('{}',{status:200}));vi.stubGlobal('fetch',fetch);
    await fetchDocument('P/1');
    expect(fetch.mock.calls[0][0]).toContain('/api/v1/projects/P%2F1/document');
    await saveDocument('P/1',{document_id:'D',expected_version:4,expected_document_sequence:7,
      requirements:{project_id:'P',archetype:'DB',items:[],is_valid:false,validation_errors:[],validation_warnings:[]}});
    expect(fetch.mock.calls[1][1]).toMatchObject({method:'PUT'});
    expect(JSON.parse((fetch.mock.calls[1][1] as RequestInit).body as string)).toMatchObject({expected_version:4,expected_document_sequence:7});
    await fetchRevision('P/1','R/2');
    expect(fetch.mock.calls[2][0]).toContain('/projects/P%2F1/revisions/R%2F2');
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
