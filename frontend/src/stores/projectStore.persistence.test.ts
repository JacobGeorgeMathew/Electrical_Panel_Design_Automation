import {beforeEach,describe,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({listProjects:vi.fn(),fetchArchetypes:vi.fn(),fetchProject:vi.fn(),fetchDesign:vi.fn(),fetchRevisions:vi.fn(),updateProject:vi.fn(),generateDesign:vi.fn(),restoreRevision:vi.fn(),startCadJob:vi.fn(),fetchCadJob:vi.fn()}));
vi.mock('../api/client',async(importOriginal)=>({...await importOriginal<typeof import('../api/client')>(),...api}));
import {useProjectStore} from './projectStore';

const project={id:'P1',database_id:'uuid',name:'Saved panel',archetype:'DB',archetype_version_id:'v1',requirements:{incomer_rating:250},configuration:{},lock_version:2,current_revision_id:'R1'};
const design={cem:{components:[],requirements:[]},pdm:{components:[]},schematic:{},cad:{},artifacts:[],revision_id:'R1',revision_no:1,lock_version:2,is_stale:false};
beforeEach(()=>{
  vi.clearAllMocks();
  useProjectStore.setState({projectId:'',hasUnsavedChanges:false,requirementValues:{},savedRequirementValues:{},projectConfiguration:{},savedConfiguration:{},isGenerating:false,isSaving:false,errorMessage:null});
  api.listProjects.mockResolvedValue([project]);api.fetchArchetypes.mockResolvedValue([{code:'DB'}]);
  api.fetchProject.mockResolvedValue(project);api.fetchDesign.mockResolvedValue(design);api.fetchRevisions.mockResolvedValue([{id:'R1',revision_no:1}]);
});

describe('persisted project state',()=>{
  it('reopens stored CEM/PDM without regenerating the design',async()=>{
    await useProjectStore.getState().initializeProjects();
    expect(useProjectStore.getState().projectName).toBe('Saved panel');
    expect(useProjectStore.getState().currentRevisionId).toBe('R1');
    expect(api.generateDesign).not.toHaveBeenCalled();
  });
  it('retains unsaved edits on network failure and blocks accidental project changes',async()=>{
    await useProjectStore.getState().openProject('P1');
    useProjectStore.getState().setRequirementValue('incomer_rating',400);
    api.updateProject.mockRejectedValue(new Error('Backend unavailable'));
    await useProjectStore.getState().saveCurrentProject();
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
    expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(400);
    api.fetchProject.mockClear();
    await useProjectStore.getState().openProject('P2');
    expect(api.fetchProject).not.toHaveBeenCalled();
  });
  it('sends the expected version and project configuration when generating',async()=>{
    await useProjectStore.getState().openProject('P1');
    useProjectStore.getState().setProjectConfiguration({enclosure_id:'E1',enclosure_parameters:{width_mm:800}});
    api.generateDesign.mockResolvedValue({...design,revision_id:'R2',revision_no:2,lock_version:3});
    api.fetchProject.mockResolvedValue({...project,lock_version:3});
    await useProjectStore.getState().runDesignPipeline({incomer_rating:400});
    expect(api.generateDesign).toHaveBeenCalledWith('P1',{incomer_rating:400},2,{enclosure_id:'E1',enclosure_parameters:{width_mm:800}});
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(false);
    expect(useProjectStore.getState().currentRevisionId).toBe('R2');
  });
  it('refreshes a saved preview only after its job is ready',async()=>{
    await useProjectStore.getState().openProject('P1');
    api.startCadJob.mockResolvedValue({id:'A1',project_revision_id:'R1',status:'PENDING'});
    api.fetchCadJob.mockResolvedValue({id:'A1',status:'READY',url:'/api/artifacts/A1/content',file_format:'GLB'});
    await useProjectStore.getState().refreshCadPreview();
    expect(useProjectStore.getState().cadJobStatus).toBe('READY');
    expect(useProjectStore.getState().artifacts[0].id).toBe('A1');
  });
});
