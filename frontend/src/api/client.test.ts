import {afterEach,describe,expect,it,vi} from 'vitest';
import {request,ApiError} from './client';
afterEach(()=>{vi.unstubAllGlobals();});

describe('API failures and cancellation',()=>{
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
