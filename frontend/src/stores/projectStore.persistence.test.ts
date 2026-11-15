import {beforeEach,describe,expect,it,vi} from 'vitest';
import fixture from '../types/fixtures/document-v1.json';
import {ApiError} from '../api/client';
import {documentStatus,documentSave} from './documentStore';
const api=vi.hoisted(()=>({fetchDocument:vi.fn(),saveDocument:vi.fn(),fetchRevision:vi.fn(),createProject:vi.fn(),saveRecovery:vi.fn(),markProjectOpened:vi.fn(),listProjects:vi.fn(),fetchArchetypes:vi.fn(),fetchProject:vi.fn(),fetchDesign:vi.fn(),fetchRevisions:vi.fn(),updateProject:vi.fn(),generateDesign:vi.fn(),restoreRevision:vi.fn(),startCadJob:vi.fn(),fetchCadJob:vi.fn()}));
vi.mock('../api/client',async(importOriginal)=>({...await importOriginal<typeof import('../api/client')>(),...api}));
import {useProjectStore} from './projectStore';

const project={id:'P1',database_id:'uuid',name:'Saved panel',archetype:'DB',archetype_version_id:'v1',requirements:{incomer_rating:250},configuration:{},lock_version:2,current_revision_id:'R1'};
const design={cem:{components:[],requirements:[]},pdm:{components:[],routes:[]},schematic:{},cad:{},artifacts:[],revision_id:'R1',revision_no:1,lock_version:2,is_stale:false};
beforeEach(()=>{
  vi.clearAllMocks();
  localStorage.clear();
  useProjectStore.setState({document:null,viewedRevisionId:null,publishedDesign:null,projectId:'',hasUnsavedChanges:false,requirementValues:{},savedRequirementValues:{},projectConfiguration:{},savedConfiguration:{},isGenerating:false,isSaving:false,errorMessage:null,pendingRecovery:null,editSequence:0});
  api.fetchDocument.mockRejectedValue(new ApiError('Explicit conversion required',409,'DOCUMENT_NOT_INITIALIZED'));
  api.listProjects.mockResolvedValue([project]);api.fetchArchetypes.mockResolvedValue([{code:'DB'}]);
  api.markProjectOpened.mockResolvedValue(project);api.fetchProject.mockResolvedValue(project);api.fetchDesign.mockResolvedValue(design);api.fetchRevisions.mockResolvedValue([{id:'R1',revision_no:1}]);
});

const workingDocument=()=>({...fixture,content_sha256:'a'.repeat(64),
  document:{...fixture.document,lock_version:2,configuration:{},document_sequence:0},
  snapshots:{...fixture.snapshots,requirements:{...fixture.snapshots.requirements,items:[{
    id:'incomer_rating',label:'Incomer',value:250,unit:'A',state:'PROPOSED',source:'USER',message:null,
  }]}}});

describe('versioned document adapter',()=>{
  it('saves and reopens the draft without publication and excludes workspace display state',async()=>{
    const view=workingDocument();
    api.fetchDocument.mockResolvedValue(view);
    await useProjectStore.getState().openProject('P1');
    useProjectStore.getState().setRequirementValue('incomer_rating','unfinished');
    useProjectStore.getState().selectObject('Q1');
    useProjectStore.getState().toggleWireVisibility();
    const request=documentSave(useProjectStore.getState());
    expect(request).toMatchObject({document_id:view.document.document_id,expected_version:2,expected_document_sequence:0});
    expect(request).not.toHaveProperty('workspace');
    const saved={...view,content_sha256:'b'.repeat(64),document:{...view.document,document_sequence:1,lock_version:3},
      snapshots:{...view.snapshots,requirements:request.requirements}};
    api.saveDocument.mockResolvedValue(saved);
    api.updateProject.mockResolvedValue({...project,lock_version:4,workspace:{}});
    await useProjectStore.getState().saveCurrentProject();
    expect(api.updateProject).toHaveBeenCalledWith('P1',3,expect.not.objectContaining({requirements:expect.anything()}));
    expect(documentStatus(useProjectStore.getState())).toMatchObject({saveLabel:'Saved draft',dirtyOutput:true});
    api.fetchDocument.mockResolvedValue({...saved,document:{...saved.document,lock_version:4}});
    await useProjectStore.getState().openProject('P1');
    expect(useProjectStore.getState().requirementValues).toEqual({incomer_rating:'unfinished'});
    expect(api.generateDesign).not.toHaveBeenCalled();
    expect(api.restoreRevision).not.toHaveBeenCalled();
  });

  it.each(['NETWORK_ERROR','DOCUMENT_CONFLICT'])('retains draft and fences after %s',async(code)=>{
    api.fetchDocument.mockResolvedValue(workingDocument());
    await useProjectStore.getState().openProject('P1');
    useProjectStore.getState().setRequirementValue('incomer_rating',400);
    api.saveDocument.mockRejectedValue(new ApiError(code,409,code));
    await useProjectStore.getState().saveCurrentProject();
    expect(useProjectStore.getState()).toMatchObject({hasUnsavedChanges:true,lockVersion:2,requirementValues:{incomer_rating:400}});
    expect(api.updateProject).not.toHaveBeenCalled();
    expect(api.generateDesign).not.toHaveBeenCalled();
  });

  it('retains local overlays and the advanced document fence after a partial Save failure',async()=>{
    const view=workingDocument();api.fetchDocument.mockResolvedValue(view);
    await useProjectStore.getState().openProject('P1');
    useProjectStore.getState().setRequirementValue('incomer_rating',400);
    api.saveDocument.mockResolvedValue({...view,document:{...view.document,lock_version:3,document_sequence:1}});
    api.updateProject.mockRejectedValue(new Error('Overlay conflict'));
    await useProjectStore.getState().saveCurrentProject();
    expect(useProjectStore.getState()).toMatchObject({hasUnsavedChanges:true,lockVersion:3,requirementValues:{incomer_rating:400}});
    expect(useProjectStore.getState().document?.document.document_sequence).toBe(1);
  });

  it('blocks all document writes in historical views and returns to the saved draft',async()=>{
    api.fetchDocument.mockResolvedValue(workingDocument());
    await useProjectStore.getState().openProject('P1');
    api.fetchRevision.mockResolvedValue({...design,revision_id:'OLD',revision_no:1,is_non_current:true,
      output_status:'MISSING_OUTPUTS',cem:{...design.cem,requirements:[{id:'incomer_rating',value:63}]}});
    await useProjectStore.getState().viewRevision('OLD');
    const state=useProjectStore.getState();
    expect(documentStatus(state)).toMatchObject({readOnly:true,unsupported:true,saveLabel:'Historical read-only'});
    state.setRequirementValue('incomer_rating',800);state.setProjectConfiguration({enclosure_id:'other'});
    state.setSchematicDraft({changed:true});state.updateEditorTransform('Q1',{x:100});state.resetEditorDraft();
    await state.saveCurrentProject();await state.runDesignPipeline();await state.restoreSavedRevision('R1');
    await state.applyChangePropagation('incomer_rating',800);await state.autosave();await state.discardRecovery();
    await state.validateCurrentPlacement();await state.refreshCadPreview();
    expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(63);
    for(const method of [api.saveDocument,api.updateProject,api.generateDesign,api.restoreRevision,api.saveRecovery,api.startCadJob])expect(method).not.toHaveBeenCalled();
    await state.returnToDocument();
    expect(useProjectStore.getState().viewedRevisionId).toBeNull();
    expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(250);
  });

  it('does not fall back to the legacy document after a document load failure',async()=>{
    useProjectStore.setState({requirementValues:{local:'retained'}});
    api.fetchDocument.mockRejectedValue(new ApiError('Unavailable'));
    await useProjectStore.getState().openProject('P1');
    expect(useProjectStore.getState().requirementValues).toEqual({local:'retained'});
    expect(useProjectStore.getState().errorMessage).toContain('Unavailable');
  });

  it('keeps Publish explicit, uses saved inputs and reloads the working draft after publication',async()=>{
    const view=workingDocument();api.fetchDocument.mockResolvedValue(view);
    await useProjectStore.getState().openProject('P1');
    useProjectStore.getState().setRequirementValue('incomer_rating',400);
    await useProjectStore.getState().runDesignPipeline();
    expect(api.generateDesign).not.toHaveBeenCalled();
    api.saveDocument.mockResolvedValue({...view,document:{...view.document,document_sequence:1,lock_version:3},
      snapshots:{...view.snapshots,requirements:documentSave(useProjectStore.getState()).requirements}});
    api.updateProject.mockResolvedValue({...project,lock_version:4});
    await useProjectStore.getState().saveCurrentProject();
    expect(api.generateDesign).not.toHaveBeenCalled();
    const saved=useProjectStore.getState().document!;
    api.fetchDocument.mockResolvedValue({...saved,document:{...saved.document,lock_version:5}});
    api.generateDesign.mockResolvedValue({...design,revision_id:'R2',revision_no:2,lock_version:5,
      output_status:'COMPLETE',output_manifest:{source_document:{sha256:saved.content_sha256}},
      cem:{...design.cem,requirements:[{id:'incomer_rating',value:400}]}});
    api.fetchProject.mockResolvedValue({...project,lock_version:5,requirements:{legacy:'must not replace draft'}});
    await useProjectStore.getState().runDesignPipeline();
    expect(api.generateDesign).toHaveBeenCalledWith('P1',{incomer_rating:400},4,{});
    expect(useProjectStore.getState().requirementValues).toEqual({incomer_rating:400});
    expect(documentStatus(useProjectStore.getState())).toMatchObject({saveLabel:'Saved draft',dirtyOutput:false});
  });
});

it('retains an incompatible recovery checkpoint and all edits after explicit Recover',async()=>{
  const checkpoint={schema_version:2,recovery_sequence:3,base_version:1,saved_at:'2026-11-15T00:00:00Z',
    document:{schema_version:2,baseDocument:null,baseRevisionId:'OLD',requirements:{unfinished:'-'},configuration:{},
      workspace:{editorTransforms:{C1:{x:1,y:2,z:3,rotation_deg:0}}}}};
  api.markProjectOpened.mockResolvedValue({...project,recovery_version:3,recovery:checkpoint});
  await useProjectStore.getState().openProject('P1');
  useProjectStore.getState().recoverChanges();
  expect(useProjectStore.getState().pendingRecovery).toEqual(checkpoint);
  expect(useProjectStore.getState().requirementValues).toEqual(project.requirements);
  expect(useProjectStore.getState().errorMessage).toContain('retained');
  expect(api.generateDesign).not.toHaveBeenCalled();
});

it('keeps edits and the browser checkpoint when a discard response arrives late',async()=>{
  await useProjectStore.getState().openProject('P1');
  useProjectStore.getState().setRequirementValue('num_feeders',16);
  let resolve!:(value:any)=>void;
  api.saveRecovery.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const pending=useProjectStore.getState().discardLocalEdits();
  useProjectStore.getState().setRequirementValue('num_feeders',20);
  const {writeRecovery,readRecovery}=await import('./projectRecovery');
  const {recoveryDocument}=await import('./projectStore');
  writeRecovery('P1',{base_version:2,saved_at:new Date().toISOString(),document:recoveryDocument(useProjectStore.getState())});
  resolve({...project,recovery_version:4});await pending;
  expect(useProjectStore.getState().requirementValues.num_feeders).toBe(20);
  expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
  expect(readRecovery('P1')?.document.requirements.num_feeders).toBe(20);
  expect(useProjectStore.getState().recoveryVersion).toBe(4);
});

it('retains edits made while generation is in flight against their original base',async()=>{
  await useProjectStore.getState().openProject('P1');
  let resolve!:(value:any)=>void;
  api.generateDesign.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const pending=useProjectStore.getState().runDesignPipeline();
  useProjectStore.getState().setRequirementValue('num_feeders',20);
  api.fetchProject.mockResolvedValue({...project,lock_version:3,current_revision_id:'R2'});
  resolve({...design,lock_version:3,revision_id:'R2'});await pending;
  const {readRecovery}=await import('./projectRecovery');
  expect(readRecovery('P1')?.document.requirements.num_feeders).toBe(20);
  expect(useProjectStore.getState().pendingRecovery?.document.baseRevisionId).toBe('R1');
  useProjectStore.getState().recoverChanges();
  expect(useProjectStore.getState().pendingRecovery).not.toBeNull();
});

it('retains edits after recovery conflict and autosaves without generating',async()=>{
  await useProjectStore.getState().openProject('P1');
  useProjectStore.getState().setRequirementValue('num_feeders','unfinished');
  api.saveRecovery.mockRejectedValue(new Error('RECOVERY_CONFLICT'));
  await useProjectStore.getState().autosave();
  expect(useProjectStore.getState().requirementValues.num_feeders).toBe('unfinished');
  expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
  expect(useProjectStore.getState().autosaveStatus).toContain('RECOVERY_CONFLICT');
  expect(api.generateDesign).not.toHaveBeenCalled();
  expect(api.saveRecovery.mock.calls[0][3]).toMatchObject({schema_version:2,baseDocument:null,baseRevisionId:'R1'});
});

it('reopens a versioned browser checkpoint and recovers only on explicit request',async()=>{
  const {writeRecovery,readRecovery}=await import('./projectRecovery');
  const checkpoint={schema_version:2,recovery_sequence:0,base_version:2,saved_at:'2026-11-15T00:00:00Z',
    document:{schema_version:2,baseDocument:null,baseRevisionId:'R1',requirements:{num_feeders:'unfinished'},
      configuration:{},workspace:{editorTransforms:{}}}};
  writeRecovery('P1',checkpoint);
  await useProjectStore.getState().openProject('P1');
  expect(useProjectStore.getState().pendingRecovery).toEqual(checkpoint);
  expect(useProjectStore.getState().requirementValues).toEqual(project.requirements);
  useProjectStore.getState().recoverChanges();
  expect(useProjectStore.getState().requirementValues.num_feeders).toBe('unfinished');
  expect(readRecovery('P1')).toEqual(checkpoint);
  expect(api.generateDesign).not.toHaveBeenCalled();
});

describe('persisted project state',()=>{
  it('reopens stored CEM/PDM without regenerating the design',async()=>{
    await useProjectStore.getState().initializeProjects();
    expect(useProjectStore.getState().projectId).toBe('');
    await useProjectStore.getState().openProject('P1');
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

it('creates an empty project without inheriting the previous requirements or design',async()=>{
  useProjectStore.setState({requirementValues:{num_feeders:48},cem:{components:[{id:'OLD'}]} as any});
  api.createProject.mockResolvedValue({...project,id:'NEW',current_revision_id:null,requirements:{num_feeders:12}});
  await useProjectStore.getState().createNewProject('New board','DB','v1',{description:'Site board',location:'Site'});
  expect(api.createProject).toHaveBeenCalledWith('New board',{},'DB','v1',{description:'Site board',location:'Site'});
  expect(useProjectStore.getState().cem).toBeNull();
  expect(useProjectStore.getState().pdm).toBeNull();
});
it('does not discard newer edits when a save finishes',async()=>{
  await useProjectStore.getState().openProject('P1');
  useProjectStore.getState().setRequirementValue('num_feeders',16);
  let resolve!:(value:any)=>void;
  api.updateProject.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const saving=useProjectStore.getState().saveCurrentProject();
  useProjectStore.getState().setRequirementValue('num_feeders',20);
  resolve({...project,lock_version:3,requirements:{num_feeders:16}});
  await saving;
  expect(useProjectStore.getState().requirementValues.num_feeders).toBe(20);
  expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
  expect(useProjectStore.getState().lockVersion).toBe(3);
});
it('saves before closing and returns to the dashboard',async()=>{
  await useProjectStore.getState().openProject('P1');
  useProjectStore.getState().setRequirementValue('num_feeders',16);
  api.updateProject.mockResolvedValue({...project,lock_version:3});
  await useProjectStore.getState().saveAndClose();
  expect(api.updateProject).toHaveBeenCalled();
  expect(useProjectStore.getState().projectId).toBe('');
});
it('offers durable recovery and applies it only when requested',async()=>{
  api.markProjectOpened.mockResolvedValue({...project,recovery_version:2,recovery:{base_version:2,saved_at:'2026-11-01T00:00:00Z',document:{requirements:{num_feeders:16},configuration:{},workspace:{},baseRevisionId:'R1'}}});
  await useProjectStore.getState().openProject('P1');
  expect(useProjectStore.getState().requirementValues.num_feeders).toBeUndefined();
  useProjectStore.getState().recoverChanges();
  expect(useProjectStore.getState().requirementValues.num_feeders).toBe(16);
  expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
});
it('ignores an old project save after another project opens',async()=>{
  await useProjectStore.getState().openProject('P1');
  useProjectStore.getState().setRequirementValue('num_feeders',16);
  let resolve!:(value:any)=>void;
  api.updateProject.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const pending=useProjectStore.getState().saveCurrentProject();
  api.markProjectOpened.mockResolvedValue({...project,id:'P2',name:'Other project'});
  await useProjectStore.getState().openProject('P2',true);
  resolve({...project,lock_version:3});await pending;
  expect(useProjectStore.getState().projectId).toBe('P2');
  expect(useProjectStore.getState().projectName).toBe('Other project');
  expect(useProjectStore.getState().isSaving).toBe(false);
});
it('does not attach a late CAD result to a different project',async()=>{
  await useProjectStore.getState().openProject('P1');
  api.startCadJob.mockResolvedValue({id:'OLD',status:'PENDING'});
  let resolve!:(value:any)=>void;
  api.fetchCadJob.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const pending=useProjectStore.getState().refreshCadPreview();
  await vi.waitFor(()=>expect(api.fetchCadJob).toHaveBeenCalled());
  api.markProjectOpened.mockResolvedValue({...project,id:'P2'});
  await useProjectStore.getState().openProject('P2');
  resolve({id:'OLD',status:'READY',file_format:'GLB'});await pending;
  expect(useProjectStore.getState().projectId).toBe('P2');
  expect(useProjectStore.getState().artifacts).toEqual([]);
});
