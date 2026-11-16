import React from 'react';
import {createRoot} from 'react-dom/client';
import {PerspectiveCamera, Vector3} from 'three';
// @ts-expect-error Transitive viewer dependency has no TypeScript declarations.
import {configureTextBuilder} from 'troika-three-text';
import {Panel3DViewer} from '../src/components/threeD/Panel3DViewer';
import {fitPanelCamera} from '../src/components/threeD/cameraFit';
import {useProjectStore} from '../src/stores/projectStore';
import {useCommandStore, type CommandProposal} from '../src/stores/commandStore';
import {useWorkspaceStore} from '../src/stores/workspaceStore';
import {documentFields, documentSave} from '../src/stores/documentStore';
import {fetchDocument, saveDocument} from '../src/api/client';
import type {PhysicalDesignModel} from '../src/types/pdm';
import '../src/index.css';
import '../src/components/workspace/workspace.css';

// Keep text rendering offline. This installed Three.js example font is served
// only by the test Vite server; no production font or asset contract is changed.
configureTextBuilder({defaultFontURL: '/node_modules/three/examples/fonts/ttf/kenpixel.ttf'});

async function load(projectId: string) {
  useCommandStore.getState().clear();
  const view = await fetchDocument(projectId);
  // This seeded contract has positioned terminals and legacy-compatible bounds;
  // production aggregate-to-viewer synchronization belongs to the binding tasks.
  const pdm = view.snapshots.pdm as unknown as PhysicalDesignModel;
  useProjectStore.setState({...documentFields(view), projectId,
    pdm, pdmBaseline: pdm,
    activeTab: 'threeD', isLoadingProject: false, isSaving: false, isGenerating: false,
    hasUnsavedChanges: false, pendingRecovery: null, viewedRevisionId: null,
    editorTransforms: {}, editorUndoStack: [], editorRedoStack: [], selectedObjectId: null});
  useWorkspaceStore.getState().setCameraPose('front');
  return view;
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
      error: command.error && {code: command.error.code, status: command.error.status, message: command.error.message}};
  },
  propose: (proposal: CommandProposal) => useCommandStore.getState().propose(proposal),
  preview: () => useCommandStore.getState().previewProposal(),
  commit: () => useCommandStore.getState().commitProposal(),
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
  return <main style={{height: '100vh', display: 'flex', flexDirection: 'column'}}>
    <output aria-label="Harness selection">{selected || 'none'}</output>
    <Panel3DViewer/>
  </main>;
}

const projectId = new URLSearchParams(location.search).get('project');
if (!projectId) throw new Error('Harness requires an isolated project ID.');
void load(projectId).then(() => createRoot(document.getElementById('root')!).render(<Harness/>));
