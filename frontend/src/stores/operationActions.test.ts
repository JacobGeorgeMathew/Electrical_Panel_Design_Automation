import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {useProjectStore} from './projectStore';
import {useCommandStore} from './commandStore';
import {documentFields} from './documentStore';
import {commitPlacement} from './operationActions';
import fixture from '../types/fixtures/document-v1.json';
import type {DocumentView} from '../types/document';

beforeEach(()=>{
  useCommandStore.getState().clear();
  const view={...structuredClone(fixture),content_sha256:'a'.repeat(64)} as DocumentView;
  useProjectStore.setState({...documentFields(view),projectId:view.document.project_id,
    viewedRevisionId:null,isSaving:false,isGenerating:false,isLoadingProject:false,pendingRecovery:null,hasUnsavedChanges:false});
});
afterEach(()=>{vi.unstubAllGlobals();});
it('keeps preview transient and installs only server PDM; never calls routing',async()=>{
  const s=useProjectStore.getState(), c=s.pdm!.components[0], before=s.document;
  s.updateEditorTransform(c.cem_component_id,{x:140});s.updateEditorTransform(c.cem_component_id,{x:145});
  expect(useProjectStore.getState().document).toBe(before);
  expect(useProjectStore.getState().pdm).toBe(s.pdm);
  expect(useProjectStore.getState().hasUnsavedChanges).toBe(false);
  const result=structuredClone(before!);result.snapshots.pdm!.components[0].position.x=145;
  const fetch=vi.fn(async(_url:string,_options:RequestInit)=>new Response(JSON.stringify({result})));vi.stubGlobal('fetch',fetch);
  await commitPlacement();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetch.mock.calls[0][1]!.body as string).operations).toMatchObject([
    {type:'MoveComponent',parameters:{position_mm:{x:145}}}]);
  expect(useProjectStore.getState().pdm!.components[0].position.x).toBe(145);
  expect(useProjectStore.getState().editorTransforms).toEqual({});
});
it('rejects nonfinite transforms and unsupported rotation and keeps display changes engineering-free',()=>{
  const s=useProjectStore.getState(),c=s.pdm!.components[0];
  s.updateEditorTransform(c.cem_component_id,{x:NaN});s.updateEditorTransform(c.cem_component_id,{rotation_deg:90});
  s.toggleWireVisibility();s.toggleComponentVisibility(c.cem_component_id);s.toggleExplodedView();
  expect(useProjectStore.getState().editorTransforms).toEqual({});
  expect(useProjectStore.getState().document).toBe(s.document);
  expect(useCommandStore.getState().proposal).toBeNull();
});
