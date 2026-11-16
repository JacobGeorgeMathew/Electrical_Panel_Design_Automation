import {beforeEach, afterEach, describe, expect, it, vi} from 'vitest';
import {useCommandStore, type CommandProposal} from './commandStore';
import {useProjectStore} from './projectStore';
import {useWorkspaceStore} from './workspaceStore';
import documentFixture from '../types/fixtures/document-v1.json';
import requestFixture from '../types/fixtures/operation-preview-v1.json';
import type {DocumentView} from '../types/document';

const base = () => ({...structuredClone(documentFixture), content_sha256: 'a'.repeat(64)}) as DocumentView;
const proposal = (): CommandProposal => ({projectId:'project-1',key:'retry-key',kind:'operations',request:structuredClone(requestFixture) as any});
const reply = (value: unknown, status=200) => new Response(JSON.stringify(value), {status});
beforeEach(()=>{
  useCommandStore.getState().clear();
  useProjectStore.setState({projectId:'project-1',document:base(),lockVersion:3,editSequence:0,
    viewedRevisionId:null,isLoadingProject:false,isSaving:false,isGenerating:false,pendingRecovery:null});
});
afterEach(()=>{useCommandStore.getState().clear();vi.unstubAllGlobals();});

describe('shared command client',()=>{
  it('retains exact proposal/key and displays structured rejection without changing the document',async()=>{
    const saved=useProjectStore.getState().document;
    vi.stubGlobal('fetch',vi.fn(async()=>reply({error:{code:'PHYSICAL_CONSTRAINT',message:'Duct obstructed',details:{object_id:'Q1'}}},422)));
    useCommandStore.getState().propose(proposal());
    await useCommandStore.getState().commitProposal();
    expect(useCommandStore.getState().proposal).toEqual(proposal());
    expect(useCommandStore.getState().error).toMatchObject({status:422,code:'PHYSICAL_CONSTRAINT',message:'Duct obstructed',details:{details:{object_id:'Q1'}}});
    expect(useWorkspaceStore.getState().bottomTab).toBe('output');
    expect(useProjectStore.getState().document).toBe(saved);
  });
  it('previews without durable writes and applies only returned document on explicit commit',async()=>{
    const saved=useProjectStore.getState().document;
    const next=base(); next.document.document_sequence++; next.document.lock_version++;
    const fetch=vi.fn(async(url:string)=>reply(url.endsWith('/preview')?{status:'PREVIEW',candidate:next}:{status:'COMMITTED',result:next}));
    vi.stubGlobal('fetch',fetch);
    useCommandStore.getState().propose(proposal());
    await useCommandStore.getState().previewProposal();
    expect(useProjectStore.getState().document).toBe(saved);
    await useCommandStore.getState().commitProposal();
    expect(useProjectStore.getState().document).toEqual(next);
    expect(useProjectStore.getState().lockVersion).toBe(4);
    expect(fetch.mock.calls[1][0]).toContain('/document/operations/commit');
  });
  it('ignores late preview after a new proposal, local edit or project switch',async()=>{
    for (const change of ['proposal','edit','project']) {
      useProjectStore.setState({projectId:'project-1',document:base(),editSequence:0});
      let resolve!: (response:Response)=>void;
      vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(r=>{resolve=r;})));
      useCommandStore.getState().propose(proposal());
      const pending=useCommandStore.getState().previewProposal();
      if(change==='proposal')useCommandStore.getState().propose({...proposal(),key:'new-key'});
      if(change==='edit')useProjectStore.setState({editSequence:1});
      if(change==='project')useProjectStore.setState({projectId:'other'});
      resolve(reply({status:'PREVIEW'})); await pending;
      expect(useCommandStore.getState().preview).toBeNull();
      expect(useCommandStore.getState().pending).toBe(false);
    }
  });
  it('cancels a request while retaining the proposal and reuses key on retry',async()=>{
    const fetch=vi.fn((_url:string, options:RequestInit)=>new Promise<Response>((_resolve,reject)=>
      options.signal!.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')))));
    vi.stubGlobal('fetch',fetch);
    useCommandStore.getState().propose(proposal());
    const pending=useCommandStore.getState().commitProposal();
    useCommandStore.getState().cancel(); await pending;
    expect(useCommandStore.getState().proposal?.key).toBe('retry-key');
    expect(fetch.mock.calls[0][1].headers).toMatchObject({'Idempotency-Key':'retry-key'});
    const retry=vi.fn(async()=>reply({error:{code:'DOCUMENT_CONFLICT',message:'Changed'}},409));
    vi.stubGlobal('fetch',retry);
    await useCommandStore.getState().commitProposal();
    expect(retry).toHaveBeenCalledWith(expect.stringContaining('/operations/commit'),expect.objectContaining({
      headers:expect.objectContaining({'Idempotency-Key':'retry-key'}),body:JSON.stringify(requestFixture)}));
  });
  it('ignores a late commit receipt after the loaded document changes',async()=>{
    let resolve!: (response:Response)=>void;
    vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(r=>{resolve=r;})));
    useCommandStore.getState().propose(proposal());
    const pending=useCommandStore.getState().commitProposal();
    const newer=base(); newer.document.document_sequence+=2;
    useProjectStore.setState({document:newer});
    resolve(reply({status:'COMMITTED',result:base()})); await pending;
    expect(useProjectStore.getState().document).toBe(newer);
    expect(useCommandStore.getState().receipt).toBeNull();
    expect(useCommandStore.getState().proposal).toEqual(proposal());
  });
  it('sends server-owned undo intent through history with concurrency fences',async()=>{
    const fetch=vi.fn(async(_url:string,_options:RequestInit)=>reply({error:{code:'DOCUMENT_CONFLICT',message:'Changed'}},409)); vi.stubGlobal('fetch',fetch);
    useCommandStore.getState().propose({projectId:'project-1',key:'undo-key',kind:'history',request:{
      ...requestFixture,operation_id:'undo-op',before_content_sha256:'a'.repeat(64),action:'UNDO',target_batch_id:'previous',
      origin:{kind:'MANUAL',actor_id:'local-user'}} as any});
    await useCommandStore.getState().commitProposal();
    expect(fetch.mock.calls[0][0]).toContain('/document/operations/history');
    expect(JSON.parse(fetch.mock.calls[0][1].body as string)).toMatchObject({action:'UNDO',base_sequence:7,expected_version:3});
    expect(useCommandStore.getState().proposal?.kind).toBe('history');
    expect(useCommandStore.getState().error?.code).toBe('DOCUMENT_CONFLICT');
  });
});
