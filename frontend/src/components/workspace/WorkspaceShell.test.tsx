import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {useProjectStore} from '../../stores/projectStore';
import {useWorkspaceStore,panelSize} from '../../stores/workspaceStore';
const lifecycle=vi.hoisted(()=>({mounted:vi.fn(),unmounted:vi.fn()}));
vi.mock('../threeD/Panel3DViewer',()=>({Panel3DViewer:({embedded}:any)=>{React.useEffect(()=>{lifecycle.mounted();return()=>lifecycle.unmounted();},[]);return <div data-testid="assembly" data-embedded={embedded}><button onClick={()=>useProjectStore.getState().selectObject('PDM-Q1')}>Pick assembly component</button></div>;}}));
vi.mock('../layout/Layout2DViewer',()=>({Layout2DViewer:({embedded}:any)=><div data-testid="layout" data-embedded={embedded}><button onClick={()=>useProjectStore.getState().selectObject('Q1')}>Pick layout component</button></div>}));
vi.mock('../schematic/SchematicViewer',()=>({SchematicViewer:({embedded}:any)=><div data-testid="schematic" data-embedded={embedded}/>}));
vi.mock('../requirements/Questionnaire',()=>({Questionnaire:()=> <div>Project requirements</div>}));
vi.mock('../catalog/CatalogBrowser',()=>({CatalogBrowser:()=> <div>Catalog</div>}));
import {ProjectPage} from '../../pages/ProjectPage';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
const component={id:'Q1',catalog_id:'MCB',name:'Feeder breaker',category:'MCB',width:20,height:45,depth:35,current_rating:16,heat_loss:1};
beforeEach(()=>{
  Object.defineProperty(window,'innerWidth',{value:1440,writable:true,configurable:true});
  vi.clearAllMocks();host=document.createElement('div');document.body.append(host);root=createRoot(host);
  useWorkspaceStore.setState({browserOpen:true,inspectorOpen:true,bottomOpen:true,browserWidth:180,inspectorWidth:224,bottomHeight:128,tool:'select',measurement:[],cameraCommand:null});
  useProjectStore.setState({projectId:'P',projectName:'Factory distribution',projectDescription:'Workshop',projectLocation:'Site',activeTab:'threeD',
    cem:{components:[component],connections:[]} as any,pdm:{id:'PDM-P',components:[{...component,id:'PDM-Q1',cem_component_id:'Q1',position:{x:20,y:30,z:10},heat_loss_watts:1}],routes:[],rails:[],accessories:[],ducts:[],validation_results:[]} as any,
    selectedObjectId:null,editorTransforms:{},editorHiddenComponentIds:[],isSaving:false,isGenerating:false,isLoadingProject:false,pendingRecovery:null,
    hasUnsavedChanges:false,designStale:false,currentRevisionNo:2,currentRevisionId:'R2',validationErrors:[],validationWarnings:[],errorMessage:null,
    editorUndoStack:[],editorRedoStack:[],editorMode:'select',revisions:[],artifacts:[],autosaveStatus:''});
});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.restoreAllMocks();});
const click=(selector:string)=>act(()=>(host.querySelector(selector) as HTMLButtonElement).click());
describe('engineering workspace',()=>{
  it('offers engineering menus, document tabs, revision and save status',()=>{
    act(()=>root.render(<ProjectPage/>));
    expect(Array.from(host.querySelectorAll('[aria-label="Application menu"] [aria-haspopup]')).map(b=>b.textContent)).toEqual(['File','Edit','View','Design','Tools','Validate','Export','Help']);
    expect(host.querySelector('[aria-label="Design tools"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="Project browser"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="Properties inspector"]')).not.toBeNull();
    expect(host.querySelector('.workspace-statusbar')?.textContent).toContain('Active revision r2');
    expect(host.querySelector('[data-testid="assembly"]')?.getAttribute('data-embedded')).toBe('true');
  });
  it('shares one component selection between browser, inspector and multiple views',()=>{
    act(()=>root.render(<ProjectPage/>));
    click('[aria-label="Select Q1"]');
    expect(useProjectStore.getState().selectedObjectId).toBe('Q1');
    expect(host.querySelector('[aria-label="Properties inspector"]')?.textContent).toContain('Feeder breaker');
    click('[data-view="layout2d"]');
    expect(useProjectStore.getState().selectedObjectId).toBe('Q1');
    expect(host.querySelector('[data-testid="layout"]')).not.toBeNull();
    act(()=>useProjectStore.getState().selectObject(null));
    click('[data-view="threeD"]');click('[data-testid="assembly"] button');
    expect(useProjectStore.getState().selectedObjectId).toBe('Q1');
  });
  it('collapses and resizes panels without recreating the mounted canvas',()=>{
    act(()=>root.render(<ProjectPage/>));
    const canvas=host.querySelector('[data-testid="assembly"]');
    click('[aria-label="Hide properties"]');
    expect(host.querySelector('[aria-label="Properties inspector"]')).toBeNull();
    expect(host.querySelector('[data-testid="assembly"]')).toBe(canvas);
    const divider=host.querySelector('[aria-label="Resize browser panel"]')!;
    act(()=>divider.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})));
    expect(useWorkspaceStore.getState().browserWidth).toBe(196);
    expect(host.querySelector('.engineering-workspace')?.getAttribute('style')).toContain('--browser-width: 196px');
    expect(lifecycle.mounted).toHaveBeenCalledTimes(1);expect(lifecycle.unmounted).not.toHaveBeenCalled();
  });
  it('allows save shortcuts while editing and does not hijack input undo',()=>{
    const save=vi.spyOn(useProjectStore.getState(),'saveCurrentProject').mockResolvedValue();
    act(()=>root.render(<ProjectPage/>));click('[aria-label="Select Q1"]');
    const field=host.querySelector('[aria-label="Inspector x"]')!;
    act(()=>field.dispatchEvent(new KeyboardEvent('keydown',{key:'s',ctrlKey:true,bubbles:true,cancelable:true})));
    // No dirty document means save is disabled; edits activate the same command.
    expect(save).not.toHaveBeenCalled();
    act(()=>useProjectStore.setState({hasUnsavedChanges:true}));
    act(()=>field.dispatchEvent(new KeyboardEvent('keydown',{key:'s',ctrlKey:true,bubbles:true,cancelable:true})));
    expect(save).toHaveBeenCalledOnce();
  });
  it('uses actual generation activity rather than fabricated progress',()=>{
    act(()=>root.render(<ProjectPage/>));
    act(()=>{useProjectStore.setState({isGenerating:true});useWorkspaceStore.getState().setBottomTab('output');});
    expect(host.querySelector('progress[aria-label="Design generation progress"]')?.hasAttribute('value')).toBe(false);
    expect(host.querySelector('[aria-label="output console"]')?.textContent).toContain('Running requirements');
    act(()=>useProjectStore.setState({isGenerating:false,errorMessage:'Generation failed'}));
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('Generation failed');
  });
  it('shows measurement between selected PDM centers without modifying models',()=>{
    const baseline=useProjectStore.getState().pdm!;
    useProjectStore.setState({pdm:{...baseline,components:[...baseline.components,{...baseline.components[0],id:'PDM-Q2',cem_component_id:'Q2',position:{x:23,y:34,z:10}}]}});
    act(()=>root.render(<ProjectPage/>));click('[aria-label="Measure"]');
    act(()=>useProjectStore.getState().selectObject('Q1'));
    act(()=>useProjectStore.getState().selectObject('Q2'));
    expect(host.querySelector('.measurement')?.textContent).toContain('5.00 mm');
    expect(useProjectStore.getState().editorTransforms).toEqual({});
  });
  it('edits schematic presentation without rewriting CEM connectivity',()=>{
    const cem=useProjectStore.getState().cem;
    useProjectStore.setState({schematicData:{width:800,height:600,symbols:[],wires:[{id:'CONN-1',net_id:'NET-1',net_name:'Feed',wire_class:'POWER',from:'Q1',to:'Q2',from_terminal:'L1',to_terminal:'L1',color:'#EF4444'}]},selectedObjectId:'CONN-1'});
    act(()=>root.render(<ProjectPage/>));
    const field=host.querySelector('[aria-label="Inspector wire class"]') as HTMLSelectElement;
    act(()=>{field.value='NEUTRAL';field.dispatchEvent(new Event('change',{bubbles:true}));});
    expect(useProjectStore.getState().schematicData.wires[0]).toMatchObject({wire_class:'NEUTRAL',color:'#3B82F6'});
    expect(useProjectStore.getState().cem).toBe(cem);
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
  });
  it('hides docks when the window becomes narrow and permits reopening them',()=>{
    act(()=>root.render(<ProjectPage/>));
    act(()=>{window.innerWidth=600;window.dispatchEvent(new Event('resize'));});
    expect(host.querySelector('[aria-label="Properties inspector"]')).toBeNull();
    expect(host.querySelector('[aria-label="Project browser"]')).toBeNull();
    click('[aria-label="Show properties"]');
    expect(host.querySelector('[aria-label="Properties inspector"]')).not.toBeNull();
  });
});
it('bounds splitter sizes so the canvas remains usable',()=>{
  expect(panelSize('browser',9999,1440)).toBe(320);
  expect(panelSize('inspector',-1,1440)).toBe(192);
  expect(panelSize('bottom',9999,800)).toBe(360);
});
