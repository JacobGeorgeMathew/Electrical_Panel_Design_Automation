import React from 'react';
import {createRoot} from 'react-dom/client';
import {Box3, Group, Object3D, PerspectiveCamera, Raycaster, Vector2, Vector3} from 'three';
import {_roots} from '@react-three/fiber';
// @ts-expect-error Transitive viewer dependency has no TypeScript declarations.
import {configureTextBuilder} from 'troika-three-text';
import {Panel3DViewer} from '../src/components/threeD/Panel3DViewer';
import {Layout2DViewer} from '../src/components/layout/Layout2DViewer';
import {PropertiesInspector} from '../src/components/workspace/PropertiesInspector';
import {useWorkspaceCommands} from '../src/components/workspace/useWorkspaceCommands';
import {SchematicViewer} from '../src/components/schematic/SchematicViewer';
import {CatalogBrowser} from '../src/components/catalog/CatalogBrowser';
import {fitPanelCamera} from '../src/components/threeD/cameraFit';
import {useProjectStore} from '../src/stores/projectStore';
import {useCommandStore, type CommandProposal} from '../src/stores/commandStore';
import {useWorkspaceStore} from '../src/stores/workspaceStore';
import {documentFields, documentSave} from '../src/stores/documentStore';
import {fetchDocument, fetchProject, saveDocument} from '../src/api/client';
import type {PhysicalDesignModel} from '../src/types/pdm';
import '../src/index.css';
import '../src/components/workspace/workspace.css';

// Keep text rendering offline. This installed Three.js example font is served
// only by the test Vite server; no production font or asset contract is changed.
configureTextBuilder({defaultFontURL: '/node_modules/three/examples/fonts/ttf/kenpixel.ttf'});

async function load(projectId: string) {
  useCommandStore.getState().clear();
  const [view, record] = await Promise.all([fetchDocument(projectId),fetchProject(projectId)]);
  // Production document adapter supplies authoritative view geometry. The harness
  // adds project metadata needed by the real workspace Save command.
  const pdm = view.snapshots.pdm as unknown as PhysicalDesignModel;
  useProjectStore.setState({...documentFields(view), projectId, projectName:record.name,
    recoveryVersion:record.recovery_version||0,
    errorMessage:null,
    pdm, pdmBaseline: pdm,
    activeTab: 'threeD', isLoadingProject: false, isSaving: false, isGenerating: false,
    hasUnsavedChanges: false, pendingRecovery: null, viewedRevisionId: null,
    editorTransforms: {}, editorUndoStack: [], editorRedoStack: [], selectedObjectId: null});
  useWorkspaceStore.getState().setCameraPose('front');
  return view;
}

function selectedMesh() {
  const canvas = document.querySelector('canvas')!;
  const scene = _roots.get(canvas)?.store.getState();
  let object: Object3D | undefined;
  scene?.scene.traverse(o => {
    const control = o as Object3D & {isTransformControls?: boolean; object?: Object3D};
    if (control.isTransformControls) object = control.object;
  });
  if (!scene || !object) throw new Error('Select a component and enable its move gizmo.');
  return {scene, object};
}

/** Test-only bridge to existing clients. It never writes a durable snapshot or
 * binds a pointer gesture to an operation. Production entry points exclude it. */
const bridge = {
  load,
  state: () => {
    const project = useProjectStore.getState();
    const command = useCommandStore.getState();
    return {document: project.document, selectedId: project.selectedObjectId,
      transforms: project.editorTransforms, undoCount: project.editorUndoStack.length,
      proposal: command.proposal, preview: command.preview, receipt: command.receipt,
      projectError: project.errorMessage,
      error: command.error && {code: command.error.code, status: command.error.status, message: command.error.message}};
  },
  propose: (proposal: CommandProposal) => useCommandStore.getState().propose(proposal),
  preview: () => useCommandStore.getState().previewProposal(),
  commit: () => useCommandStore.getState().commitProposal(),
  renderedX: () => {
    const state = useProjectStore.getState();
    const component = state.pdm!.components.find(c => c.cem_component_id === state.selectedObjectId)!;
    return selectedMesh().object.position.x / .01 - component.width / 2;
  },
  // Deliberate fault injection for the acceptance oracle: move only the actual
  // Three.js object, bypassing gestures/stores/HTTP. Never used by a positive test.
  shiftMeshOnly: (deltaMm: number) => {
    const {scene, object} = selectedMesh();
    object.position.x += deltaMm * .01;
    scene.invalidate();
  },
  // Read the live test canvas, rather than assuming a pixel offset from a
  // component center. Pointer events must still hit the real TransformControls.
  gizmoPoint: () => {
    const canvas=document.querySelector('canvas')!;
    const scene=_roots.get(canvas)?.store.getState();
    if(!scene)return null;
    let object: Object3D | undefined;
    scene.scene.traverse(o=>{if((o as Object3D & {isTransformControls?:boolean}).isTransformControls)object=o;});
    const control=object as unknown as {gizmo:{picker:{translate:Group}}}|undefined;
    if(!control)return null;
    scene.scene.updateMatrixWorld(true);
    const picker=control.gizmo.picker.translate;
    const axis=picker.children.find(o=>o.name==='X'&&o.visible);
    if(!axis)return null;
    const projected=new Box3().setFromObject(axis).getCenter(new Vector3()).project(scene.camera);
    const ray=new Raycaster();ray.setFromCamera(new Vector2(projected.x,projected.y),scene.camera);
    const hit=ray.intersectObject(picker,true).find(h=>h.object.visible);
    if(hit?.object.name!=='X')return null;
    const rect=canvas.getBoundingClientRect();
    return {axis:hit.object.name,x:rect.x+(projected.x+1)*rect.width/2,y:rect.y+(1-projected.y)*rect.height/2};
  },
  save: async () => {
    const project = useProjectStore.getState();
    const view = await saveDocument(project.projectId, documentSave(project));
    useProjectStore.setState(documentFields(view));
    return view;
  },
  // Front-view projection uses the same fit function/units as ResponsiveCamera.
  // Points guide real mouse events; selection must still pass Three.js raycasting.
  point: (id: string) => {
    const pdm = useProjectStore.getState().pdm!;
    const component = pdm.components.find(c => c.cem_component_id === id)!;
    const rect = document.querySelector('canvas')!.getBoundingClientRect();
    const fit = fitPanelCamera({width: pdm.enclosure_width * .01,
      height: pdm.enclosure_height * .01, depth: pdm.enclosure_depth * .01}, rect.width / rect.height);
    const distance = new Vector3(...fit.position).distanceTo(new Vector3(...fit.center));
    const camera = new PerspectiveCamera(45, rect.width / rect.height, .01, 1000);
    camera.position.set(fit.center[0], fit.center[1], fit.center[2] + distance);
    camera.lookAt(...fit.center); camera.updateMatrixWorld();
    const p = component.position;
    const point = new Vector3((p.x + component.width / 2) * .01,
      (p.y + component.height / 2) * .01, (p.z + component.depth / 2) * .01).project(camera);
    return {x: rect.x + (point.x + 1) * rect.width / 2, y: rect.y + (1 - point.y) * rect.height / 2};
  },
};
declare global {interface Window {panelE2E: typeof bridge}}
window.panelE2E = bridge;

function Harness() {
  const selected = useProjectStore(state => state.selectedObjectId);
  const tab = useProjectStore(state=>state.activeTab);
  const commands = useWorkspaceCommands(()=>{});
  return <main style={{height: '100vh', display: 'flex', flexDirection: 'column'}}>
    <output aria-label="Harness selection">{selected || 'none'}</output>
    <nav>{(['threeD','layout2d','schematic','catalog'] as const).map(tab=><button key={tab} onClick={()=>useProjectStore.getState().setActiveTab(tab)}>{tab}</button>)}
      <button disabled={commands.save.disabled} onClick={commands.save.run}>Save draft</button>
      <button disabled={commands.undo.disabled} onClick={commands.undo.run}>Undo operation</button>
      <button disabled={commands.redo.disabled} onClick={commands.redo.run}>Redo operation</button>
    </nav>
    <div style={{display:'flex',flex:1,minHeight:0}}>
      {tab==='layout2d'?<Layout2DViewer/>:tab==='schematic'?<SchematicViewer/>:tab==='catalog'?<CatalogBrowser/>:<Panel3DViewer/>}
      <div style={{width:224,flexShrink:0,overflowY:'auto'}}><PropertiesInspector/></div>
    </div>
  </main>;
}

const projectId = new URLSearchParams(location.search).get('project');
if (!projectId) throw new Error('Harness requires an isolated project ID.');
void load(projectId).then(() => createRoot(document.getElementById('root')!).render(<Harness/>));
