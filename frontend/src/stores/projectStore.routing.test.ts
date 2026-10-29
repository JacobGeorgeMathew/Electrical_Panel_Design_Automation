import {afterEach,describe,expect,it,vi} from 'vitest';
import * as client from '../api/client';
import {useProjectStore} from './projectStore';

function fixture(){
  const pdm={id:'PDM-P',project_id:'P',components:[{id:'PDM-C',cem_component_id:'C',position:{x:10,y:20,z:30},rotation_deg:0}],routes:[{id:'OLD'}],validation_results:[]} as any;
  useProjectStore.setState({projectId:'P',currentRevisionId:'R',pdm,pdmBaseline:pdm,editorTransforms:{},pendingEditorEdit:null,editorUndoStack:[],editorRedoStack:[],isValidatingPlacement:false});
  return pdm;
}
afterEach(()=>{vi.restoreAllMocks();});

describe('backend route synchronization',()=>{
  it('invalidates geometry immediately and consumes backend PDM, rather than old routes',async()=>{
    const pdm=fixture();
    vi.spyOn(client,'validatePlacement').mockResolvedValue({pdm:{...pdm,routes:[{id:'REROUTED'}]},validation_results:[],is_valid:true} as any);
    useProjectStore.getState().updateEditorTransform('C',{x:25});
    expect(useProjectStore.getState().pdm?.routes).toEqual([]);
    await useProjectStore.getState().validateCurrentPlacement();
    expect(useProjectStore.getState().pdm?.routes.map(r=>r.id)).toEqual(['REROUTED']);
  });
  it('ignores stale responses after reset and releases the validating state',async()=>{
    const pdm=fixture();let resolve!:(data:any)=>void;
    vi.spyOn(client,'validatePlacement').mockImplementation(()=>new Promise(r=>{resolve=r;}));
    useProjectStore.getState().updateEditorTransform('C',{x:25});
    const pending=useProjectStore.getState().validateCurrentPlacement();
    expect(useProjectStore.getState().isValidatingPlacement).toBe(true);
    useProjectStore.getState().resetEditorDraft();
    resolve({pdm:{...pdm,routes:[{id:'STALE'}]},validation_results:[],is_valid:true});
    await pending;
    expect(useProjectStore.getState().pdm).toBe(pdm);
    expect(useProjectStore.getState().isValidatingPlacement).toBe(false);
  });
});
