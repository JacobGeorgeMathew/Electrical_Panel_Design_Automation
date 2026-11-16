import { create } from 'zustand';
import {engineeringId, useSelectionStore} from './selectionStore';
import { CanonicalEngineeringModel } from '../types/cem';
import { PhysicalDesignModel } from '../types/pdm';
import { createProject, generateDesign, propagateChange, validatePlacement, validateRequirements,
  listProjects, fetchProject, fetchDesign, fetchRevisions, restoreRevision, updateProject, fetchArchetypes, startCadJob, fetchCadJob, markProjectOpened, saveRecovery } from '../api/client';
import type { Artifact, Archetype, DesignPackage, ProjectConfiguration, ProjectRecord, RevisionSummary } from '../types/api';

import { readRecovery, writeRecovery, clearRecovery, parseRecovery, compatibleRecovery, type Checkpoint, type RecoveryDocument } from './projectRecovery';
import type { RecoveryBaseDocument } from '../types/recovery';
import { ApiError, fetchDocument, saveDocument, fetchRevision } from '../api/client';
import { documentFields, documentSave } from './documentStore';
import type { DocumentView } from '../types/document';
import {applyHistory, canEditEngineering, commitPlacement} from './operationActions';
import {useCommandStore} from './commandStore';
import {documentSchematicGraph} from '../components/schematic/schematicGraph';

let projectRequest = 0;
let routingRequest = 0;
let openController: AbortController | null = null;

async function loadWorkingDocument(id: string, signal?: AbortSignal) {
  try { return await fetchDocument(id, signal); }
  catch (error) {
    if (error instanceof ApiError && error.code === 'DOCUMENT_NOT_INITIALIZED') return null;
    throw error;
  }
}

export type ViewTab = 'requirements' | 'schematic' | 'layout2d' | 'threeD' | 'validation' | 'bom' | 'catalog' | 'documentation';
export type EditorTransform = { x: number; y: number; z: number; rotation_deg: number };
type EditorTransformSnapshot = Record<string, EditorTransform>;
export type EditorMode = 'select' | 'translate' | 'rotate';

export interface ProjectState {
  document: DocumentView | null;
  publishedDesign: DesignPackage | null;
  viewedRevisionId: string | null;
  viewRevision: (id: string) => Promise<void>;
  returnToDocument: () => Promise<void>;
  projectDescription: string;
  projectLocation: string;
  recoveryVersion: number;
  recoveryBaseDocument: RecoveryBaseDocument | null;
  pendingRecovery: Checkpoint | null;
  editSequence: number;
  autosaveStatus: string;
  setSchematicDraft: (data:any) => void;
  recoverChanges: () => void;
  discardLocalEdits: () => Promise<void>;
  discardRecovery: () => Promise<void>;
  autosave: () => Promise<void>;
  saveAndClose: () => Promise<void>;

  projects: ProjectRecord[];
  archetypes: Archetype[];
  revisions: RevisionSummary[];
  currentRevisionId: string | null;
  currentRevisionNo: number | null;
  lockVersion: number;
  projectConfiguration: ProjectConfiguration;
  savedRequirementValues: Record<string, any>;
  savedConfiguration: ProjectConfiguration;
  hasUnsavedChanges: boolean;
  designStale: boolean;
  isLoadingProject: boolean;
  isSaving: boolean;
  artifacts: Artifact[];
  cadJobStatus: string | null;
  projectId: string;
  projectName: string;
  archetype: string;
  activeTab: ViewTab;
  selectedObjectId: string | null;
  hoveredObjectId: string | null;
  
  requirementValues: Record<string, any>;
  cem: CanonicalEngineeringModel | null;
  pdm: PhysicalDesignModel | null;
  pdmBaseline: PhysicalDesignModel | null;
  schematicData: any | null;
  cadData: any | null;
  
  diffReport: any | null;
  isDiffModalOpen: boolean;
  isGenerating: boolean;
  isValidatingPlacement: boolean;
  errorMessage: string | null;
  validationErrors: string[];
  validationWarnings: string[];

  editorTransforms: EditorTransformSnapshot;
  editorHiddenComponentIds: string[];
  editorMode: EditorMode;
  editorSnapEnabled: boolean;
  editorGridMm: number;
  editorUndoStack: EditorTransformSnapshot[];
  editorRedoStack: EditorTransformSnapshot[];
  pendingEditorEdit: EditorTransformSnapshot | null;
  
  explodedView: boolean;
  wireVisibility: boolean;
  
  setProjectId: (id: string) => void;
  setActiveTab: (tab: ViewTab) => void;
  selectObject: (id: string | null) => void;
  hoverObject: (id: string | null) => void;
  setRequirementValue: (field: string, val: any) => void;
  toggleExplodedView: () => void;
  toggleWireVisibility: () => void;
  closeDiffModal: () => void;
  clearError: () => void;
  setError: (message: string) => void;
  setEditorMode: (mode: EditorMode) => void;
  toggleEditorSnap: () => void;
  setEditorGridMm: (gridMm: number) => void;
  toggleComponentVisibility: (componentId: string) => void;
  updateEditorTransform: (componentId: string, transform: Partial<EditorTransform>) => void;
  commitEditorTransform: () => void;
  undoEditorTransform: () => void;
  redoEditorTransform: () => void;
  resetEditorDraft: () => void;
  validateCurrentRequirements: () => Promise<boolean>;
  validateCurrentPlacement: () => Promise<void>;
  createNewProject: (name: string, archetype?: string, versionId?: string, metadata?: {description?:string;location?:string}) => Promise<void>;
  initializeProjects: () => Promise<void>;
  openProject: (id: string, discardDraft?: boolean) => Promise<void>;
  closeProject: () => void;
  saveCurrentProject: () => Promise<void>;
  restoreSavedRevision: (id: string) => Promise<void>;
  setProjectConfiguration: (configuration: ProjectConfiguration) => void;
  refreshCadPreview: () => Promise<void>;
  
  runDesignPipeline: (overrides?: Record<string, any>) => Promise<void>;
  applyChangePropagation: (field: string, newValue: any) => Promise<void>;
}

const emptyDesign = { document: null, publishedDesign: null, viewedRevisionId: null, isSaving:false,isGenerating:false,isValidatingPlacement:false, cem: null, pdm: null, pdmBaseline: null, schematicData: null, cadData: null,
  currentRevisionId: null, currentRevisionNo: null, artifacts: [], editorTransforms: {}, editorHiddenComponentIds: [],
  editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null, selectedObjectId: null, hoveredObjectId: null,
  diffReport: null, isDiffModalOpen: false, cadJobStatus: null };
const projectFields = (p: ProjectRecord) => ({ projectId: p.id, projectName: p.name, archetype: p.archetype,
  requirementValues: p.requirements, savedRequirementValues: p.requirements, projectConfiguration: p.configuration,
  savedConfiguration: p.configuration, lockVersion: p.lock_version, hasUnsavedChanges: false,
  projectDescription:p.description || '', projectLocation:p.location || '', recoveryVersion:p.recovery_version || 0, recoveryBaseDocument:null, pendingRecovery:null });
const designFields = (d: DesignPackage) => ({ publishedDesign:d, isValidatingPlacement:false, cem: d.cem, pdm: d.pdm, pdmBaseline: d.pdm, schematicData: d.schematic,
  cadData: d.cad, currentRevisionId: d.revision_id, currentRevisionNo: d.revision_no, artifacts: d.artifacts,
  lockVersion: d.lock_version, designStale: d.is_stale, editorTransforms: {}, editorHiddenComponentIds: [],
  editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null });

function checkpointAfterGeneration(start: ProjectState, current: ProjectState): Partial<ProjectState> {
  if(start.editSequence===current.editSequence){clearRecovery(start.projectId);return {};}
  const checkpoint: Checkpoint={schema_version:2,recovery_sequence:current.recoveryVersion,
    base_version:current.lockVersion,saved_at:new Date().toISOString(),document:recoveryDocument(current)};
  // The new revision must not consume editor changes made against the old base.
  // Keep both an in-memory offer and the browser copy for explicit resolution.
  try{writeRecovery(start.projectId,checkpoint);}catch{/* The in-memory copy remains available. */}
  return {pendingRecovery:checkpoint,autosaveStatus:'Newer edits retained in recovery. Review their base before applying.'};
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  document:null, publishedDesign:null, viewedRevisionId:null,
  projectDescription:'', projectLocation:'', recoveryVersion:0, recoveryBaseDocument:null, pendingRecovery:null, editSequence:0, autosaveStatus:'',
  projects: [], archetypes: [], revisions: [], currentRevisionId: null, currentRevisionNo: null, lockVersion: 0,
  projectConfiguration: {}, savedRequirementValues: {}, savedConfiguration: {}, hasUnsavedChanges: false,
  designStale: false, isLoadingProject: false, isSaving: false, artifacts: [], cadJobStatus: null,
  projectId: '',
  projectName: 'Select or create a project',
  archetype: 'DB',
  activeTab: 'requirements',
  selectedObjectId: null,
  hoveredObjectId: null,
  
  requirementValues: {},
  
  cem: null,
  pdm: null,
  pdmBaseline: null,
  schematicData: null,
  cadData: null,
  diffReport: null,
  isDiffModalOpen: false,
  isGenerating: false,
  isValidatingPlacement: false,
  errorMessage: null,
  validationErrors: [],
  validationWarnings: [],
  editorTransforms: {},
  editorHiddenComponentIds: [],
  editorMode: 'select',
  editorSnapEnabled: true,
  editorGridMm: 5,
  editorUndoStack: [],
  editorRedoStack: [],
  pendingEditorEdit: null,
  
  explodedView: false,
  wireVisibility: true,
  
  setProjectId: (id) => set({ projectId: id }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  selectObject: (id) => useSelectionStore.getState().select(engineeringId(id, get())),
  hoverObject: (id) => set({ hoveredObjectId: id }),
  
  setRequirementValue: (field, val) =>
    set((state) => state.viewedRevisionId || state.isLoadingProject ? {} : ({
      requirementValues: { ...state.requirementValues, [field]: val },
      hasUnsavedChanges: true, designStale: true, editSequence: state.editSequence+1,
    })),
    
  toggleExplodedView: () => set((state) => ({ explodedView: !state.explodedView })),
  toggleWireVisibility: () => set((state) => ({ wireVisibility: !state.wireVisibility })),
  closeDiffModal: () => set({ isDiffModalOpen: false }),
  clearError: () => set({ errorMessage: null, validationErrors: [], validationWarnings: [] }),
  setError: (message) => set({ errorMessage: message }),
  setEditorMode: (mode) => {if(!get().viewedRevisionId && mode !== 'rotate')set({ editorMode: mode });},
  toggleEditorSnap: () => set((state) => ({ editorSnapEnabled: !state.editorSnapEnabled })),
  setEditorGridMm: (gridMm) => set({ editorGridMm: Number.isFinite(gridMm) && gridMm > 0 ? gridMm : 5 }),
  toggleComponentVisibility: (componentId) => set((state) => ({
    editorHiddenComponentIds: state.editorHiddenComponentIds.includes(componentId)
      ? state.editorHiddenComponentIds.filter((id) => id !== componentId)
      : [...state.editorHiddenComponentIds, componentId],
  })),
  updateEditorTransform: (componentId, transform) => set((state) => {
    if (state.viewedRevisionId || state.isLoadingProject) return {};
    if (state.document && (!canEditEngineering() || Object.values(transform).some(v=>!Number.isFinite(v)))) return {};
    const component = state.pdm?.components.find((item) => item.cem_component_id === componentId);
    if (!component) return state;
    const base: EditorTransform = {
      x: component.position.x, y: component.position.y, z: component.position.z,
      rotation_deg: component.rotation_deg || 0,
    };
    const current = state.editorTransforms[componentId] || base;
    if (state.document) {
      if (transform.rotation_deg !== undefined && transform.rotation_deg !== base.rotation_deg) return {};
      return {pendingEditorEdit: state.pendingEditorEdit || {},
        editorTransforms: {[componentId]: {...current, ...transform}}};
    }
    return {
      hasUnsavedChanges:true, designStale:true, editSequence:state.editSequence+1,
      pdm: state.pdm ? {...state.pdm,routes:[]} : null,
      pendingEditorEdit: state.pendingEditorEdit || { ...state.editorTransforms },
      editorTransforms: { ...state.editorTransforms, [componentId]: { ...current, ...transform } },
    };
  }),
  commitEditorTransform: () => {
    if(get().document){void commitPlacement();return;}
    set((state) => {
    if (!state.pendingEditorEdit || JSON.stringify(state.pendingEditorEdit) === JSON.stringify(state.editorTransforms)) {
      return { pendingEditorEdit: null };
    }
    return {
      editorUndoStack: [...state.editorUndoStack, state.pendingEditorEdit].slice(-100),
      editorRedoStack: [],
      pendingEditorEdit: null,
    };
  });},
  undoEditorTransform: () => {
    if(get().document){void applyHistory('UNDO');return;}
    set((state) => {
    if (state.viewedRevisionId) return {};
    if (!state.editorUndoStack.length) return state;
    return {
      hasUnsavedChanges:true, editSequence:state.editSequence+1,
      editorTransforms: state.editorUndoStack[state.editorUndoStack.length - 1],
      editorUndoStack: state.editorUndoStack.slice(0, -1),
      editorRedoStack: [...state.editorRedoStack, state.editorTransforms],
      pendingEditorEdit: null,
    };
  });},
  redoEditorTransform: () => {
    if(get().document){void applyHistory('REDO');return;}
    set((state) => {
    if (state.viewedRevisionId) return {};
    if (!state.editorRedoStack.length) return state;
    return {
      hasUnsavedChanges:true, editSequence:state.editSequence+1,
      editorTransforms: state.editorRedoStack[state.editorRedoStack.length - 1],
      editorRedoStack: state.editorRedoStack.slice(0, -1),
      editorUndoStack: [...state.editorUndoStack, state.editorTransforms],
      pendingEditorEdit: null,
    };
  });},
  resetEditorDraft: () => { if(get().viewedRevisionId)return;
    if(get().document){set({editorTransforms:{},pendingEditorEdit:null});return;}
    routingRequest++;set((state) => ({ isValidatingPlacement:false, hasUnsavedChanges:true,editSequence:state.editSequence+1, pdm: state.pdmBaseline || state.pdm,
    editorTransforms: {}, editorHiddenComponentIds: [], editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null, editorMode: 'select' })); },
  validateCurrentRequirements: async () => {
    if(get().viewedRevisionId)return false;
    try {
      const result = await validateRequirements(get().projectId, get().requirementValues);
      const errors = result.validation_errors || [];
      set({ validationErrors: errors, validationWarnings: result.validation_warnings || [], errorMessage: errors.length ? 'Please correct the highlighted requirement issues.' : null });
      return errors.length === 0;
    } catch (err) {
      set({ errorMessage: err instanceof Error ? err.message : String(err) });
      return false;
    }
  },
  validateCurrentPlacement: async () => {
    if(get().viewedRevisionId)return;
    if(get().document){set({errorMessage:'Working placement uses shared operations. Routing and physical validation require explicit Recompute.'});return;}
    const token=++routingRequest;
    const revision=get().currentRevisionId;
    const { pdmBaseline, pdm, editorTransforms, projectId } = get();
    const source = pdmBaseline || pdm;
    if (!source) return;
    const updatedPdm: PhysicalDesignModel = {
      ...source,
      components: source.components.map((component) => {
        const transform = editorTransforms[component.cem_component_id];
        return transform ? { ...component, position: { x: transform.x, y: transform.y, z: transform.z },
          rotation_deg: transform.rotation_deg } : component;
      }),
    };
    set({ pdm: {...updatedPdm,routes:[]}, isValidatingPlacement: true, errorMessage: null });
    try {
      const result = await validatePlacement(projectId, updatedPdm);
      if(token!==routingRequest||get().projectId!==projectId||get().currentRevisionId!==revision||get().editorTransforms!==editorTransforms)return;
      set({ pdm: result.pdm || { ...updatedPdm, validation_results: result.validation_results || [] }, isValidatingPlacement: false });
    } catch (err) {
      if(token===routingRequest&&get().projectId===projectId&&get().currentRevisionId===revision&&get().editorTransforms===editorTransforms) set({ isValidatingPlacement: false, errorMessage: err instanceof Error ? err.message : String(err) });
    }
  },
  initializeProjects: async () => {
    set({ isLoadingProject: true, errorMessage: null });
    try {
      const [projects, archetypes] = await Promise.all([listProjects(), fetchArchetypes()]);
      set({ projects, archetypes });
      set({ isLoadingProject: false });
    } catch (error) {
      set({ isLoadingProject: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  openProject: async (id, discardDraft = false) => {
    if (get().hasUnsavedChanges && !discardDraft) {
      set({ errorMessage: 'Save or discard your local edits before opening a project.' }); return;
    }
    const token = ++projectRequest;
    openController?.abort();
    openController = new AbortController();
    const signal = openController.signal;
    set({ isLoadingProject: true, errorMessage: null });
    try {
      const p = await markProjectOpened(id);
      const [revisions, design, document] = await Promise.all([
        fetchRevisions(id),
        p.current_revision_id ? fetchDesign(id, signal) : Promise.resolve(null),
        loadWorkingDocument(id, signal),
      ]);
      if (token !== projectRequest) return;
      set({ ...emptyDesign, ...projectFields(p), ...(design ? designFields(design) : {}),
        ...(document ? documentFields(document) : {}),
        revisions, isLoadingProject: false, designStale: design?.is_stale || !!document?.document.dirty_stages.length,
        validationErrors: [], validationWarnings: [], activeTab: 'requirements',
        editorTransforms:document ? {} : p.workspace?.editorTransforms || {},
        ...(document ? {} : {schematicData:p.workspace?.schematicData || design?.schematic || null}),
        pendingRecovery: [readRecovery(p.id),parseRecovery(p.recovery)].filter((c):c is Checkpoint=>!!c).sort((a,b)=>b.saved_at.localeCompare(a.saved_at))[0] || null, autosaveStatus:'', editSequence:0 });
      if(Object.keys(get().editorTransforms).length)void get().validateCurrentPlacement();
    } catch (error) {
      if (token === projectRequest) set({ isLoadingProject: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  closeProject: () => {
    if(get().isSaving || get().isGenerating || get().isLoadingProject)return;
    if (get().hasUnsavedChanges) { set({ errorMessage: 'Save or discard your local edits before closing.' }); return; }
    ++projectRequest;
    openController?.abort();
    set({ ...emptyDesign, projectId: '', projectName: 'Select or create a project', requirementValues: {},
      savedRequirementValues: {}, projectConfiguration: {}, savedConfiguration: {}, lockVersion: 0, revisions: [], designStale: false, pendingRecovery:null, autosaveStatus:'', projectDescription:'',projectLocation:'' });
  },
  viewRevision: async (id) => {
    const state=get();
    if(state.hasUnsavedChanges || state.pendingRecovery || state.isSaving || state.isGenerating || state.isLoadingProject){
      set({errorMessage:'Save or discard local edits and resolve recovery before viewing history.'});return;
    }
    const token=++projectRequest;
    ++routingRequest;
    openController?.abort();
    set({isLoadingProject:true,errorMessage:null});
    try {
      const design=await fetchRevision(state.projectId,id);
      if(token!==projectRequest)return;
      set({...designFields(design),viewedRevisionId:id,isLoadingProject:false,selectedObjectId:null,
        requirementValues:Object.fromEntries(design.cem.requirements.map(item=>[item.id,item.value]))});
    } catch(error) { if(token===projectRequest)set({isLoadingProject:false,errorMessage:error instanceof Error?error.message:String(error)}); }
  },
  returnToDocument: async () => { await get().openProject(get().projectId); },
  setProjectConfiguration: (configuration) => set(state=>state.viewedRevisionId || state.isLoadingProject ? {} : ({ projectConfiguration: configuration, hasUnsavedChanges: true, designStale: true,editSequence:state.editSequence+1 })),
  setSchematicDraft: (data) => set(state=>state.viewedRevisionId || state.isLoadingProject ? {} : ({schematicData:data,hasUnsavedChanges:true,designStale:true,editSequence:state.editSequence+1})),
  recoverChanges: () => {
    if(get().viewedRevisionId)return;
    const state=get(), checkpoint=state.pendingRecovery;
    if(!checkpoint)return;
    const d=checkpoint.document;
    if(!compatibleRecovery(checkpoint,state.lockVersion,state.currentRevisionId,state.recoveryBaseDocument)){
      set({errorMessage:'Recovery has an incompatible schema or changed document base. Your checkpoint is retained for conflict resolution. Discard only when its edits are no longer needed.'});
      return;
    }
    set({requirementValues:d.requirements,projectConfiguration:d.configuration,
      editorTransforms:d.workspace.editorTransforms||{},schematicData:d.workspace.schematicData||state.schematicData,
      hasUnsavedChanges:true,designStale:true,pendingRecovery:null,editSequence:state.editSequence+1,
      errorMessage:null});
  },
  discardLocalEdits: async () => {
    if(get().viewedRevisionId)return;
    const state=get(),token=projectRequest;
    if(state.isSaving||state.isGenerating)return;
    set({isSaving:true});
    try{
      const p=await saveRecovery(state.projectId,state.lockVersion,state.recoveryVersion,null);
      if(token!==projectRequest)return;
      if(get().editSequence!==state.editSequence){set({isSaving:false,recoveryVersion:p.recovery_version});return;}
      clearRecovery(state.projectId);
      set({isSaving:false,hasUnsavedChanges:false});
      await get().openProject(state.projectId,true);
    }catch(error){if(token===projectRequest)set({isSaving:false,errorMessage:error instanceof Error?error.message:String(error)});}
  },
  discardRecovery: async () => {
    if(get().viewedRevisionId)return;
    const state=get(), token=projectRequest;
    if(state.isSaving||state.isGenerating)return;
    set({isSaving:true});
    try {
      const p=await saveRecovery(state.projectId,state.lockVersion,state.recoveryVersion,null);
      if(token!==projectRequest)return;
      if(get().editSequence!==state.editSequence){set({isSaving:false,recoveryVersion:p.recovery_version});return;}
      clearRecovery(state.projectId);
      set({pendingRecovery:null,recoveryVersion:p.recovery_version,isSaving:false});
    }catch(error){if(token===projectRequest)set({isSaving:false,errorMessage:error instanceof Error?error.message:String(error)});}
  },
  autosave: async () => {
    if(get().viewedRevisionId)return;
    const state=get(), token=projectRequest;
    if(!state.projectId||!state.hasUnsavedChanges||state.pendingRecovery||state.isSaving||state.isGenerating)return;
    set({isSaving:true,autosaveStatus:'Saving recovery checkpoint…'});
    try{
      const p=await saveRecovery(state.projectId,state.lockVersion,state.recoveryVersion,recoveryDocument(state));
      if(token===projectRequest)set({recoveryVersion:p.recovery_version,isSaving:false,autosaveStatus:'Recovery checkpoint saved'});
    }catch(error){if(token===projectRequest)set({isSaving:false,autosaveStatus:error instanceof Error?error.message:String(error)});}
  },
  saveAndClose: async () => {
    if(get().viewedRevisionId){get().closeProject();return;}
    if(get().isSaving||get().isGenerating)return;
    if(get().hasUnsavedChanges)await get().saveCurrentProject();
    if(!get().hasUnsavedChanges)get().closeProject();
  },
  saveCurrentProject: async () => {
    if(get().viewedRevisionId)return;
    const state=get(), token=projectRequest;
    if(!state.projectId||state.isSaving||state.isGenerating||state.isLoadingProject||state.pendingRecovery)return;
    set({isSaving:true,errorMessage:null});
    try {
      let document=state.document;
      let version=state.lockVersion;
      if(document){
        document=await saveDocument(state.projectId,documentSave(state));
        if(token!==projectRequest)return;
        version=document.document.lock_version;
        // Keep the successful document fence even if the separate overlay save fails.
        const fields=documentFields(document);
        set({document,lockVersion:version,recoveryBaseDocument:fields.recoveryBaseDocument,
          savedRequirementValues:fields.savedRequirementValues,savedConfiguration:fields.savedConfiguration});
      }
      const p=await updateProject(state.projectId,version,{
        ...(document ? {} : {requirements:state.requirementValues,configuration:state.projectConfiguration}),expected_recovery_version:state.recoveryVersion,
        ...(document ? {} : {workspace:{editorTransforms:state.editorTransforms,schematicData:state.schematicData}}),
      });
      if(token!==projectRequest)return;
      const unchanged=get().editSequence===state.editSequence;
      if(unchanged)clearRecovery(state.projectId);
      set({lockVersion:p.lock_version,recoveryVersion:p.recovery_version||0,
        savedRequirementValues:document?documentFields(document).savedRequirementValues:p.requirements,savedConfiguration:document?state.projectConfiguration:p.configuration,
        hasUnsavedChanges:!unchanged,isSaving:false,pendingRecovery:null,autosaveStatus:'Project saved',
        projects:get().projects.map(row=>row.id===p.id?p:row)});
    }catch(error){if(token===projectRequest)set({isSaving:false,errorMessage:error instanceof Error?error.message:String(error)});}
  },
  createNewProject: async (name, archetype = 'DB', versionId, metadata) => {
    set({ isSaving: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const p = await createProject(name, {}, archetype, versionId, metadata);
      const document=await loadWorkingDocument(p.id);
      ++projectRequest;
      set({ ...emptyDesign, ...projectFields(p), revisions: [], projects: await listProjects(),
        ...(document?documentFields(document):{}),
        isSaving: false, designStale: false, activeTab: 'requirements',editSequence:0,autosaveStatus:'' });
    } catch (error) {
      set({ isSaving: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  restoreSavedRevision: async (id) => {
    if(get().viewedRevisionId)return;
    if(get().isSaving||get().isGenerating||get().pendingRecovery)return;
    if (get().hasUnsavedChanges) { set({ errorMessage: 'Save or discard local edits before restoring a revision.' }); return; }
    const state = get();
    const token=projectRequest;
    set({ isSaving: true, errorMessage: null });
    try {
      const result = await restoreRevision(state.projectId, id, state.lockVersion);
      const [project, revisions, document] = await Promise.all([fetchProject(state.projectId), fetchRevisions(state.projectId),
        state.document ? fetchDocument(state.projectId) : Promise.resolve(null)]);
      if(token!==projectRequest)return;
      const recovery=checkpointAfterGeneration(state,get());
      set({ ...projectFields(project), ...designFields(result), ...(document?{...documentFields(document),designStale:true}:{}), revisions, isSaving: false, ...recovery });
    } catch (error) {
      if(token===projectRequest)set({ isSaving: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  runDesignPipeline: async (overrides) => {
    if(get().viewedRevisionId)return;
    const state = get();
    if (!state.projectId) { set({ errorMessage: 'Create or open a project before generating a design.' }); return; }
    if(state.isSaving||state.isGenerating||state.isLoadingProject||state.pendingRecovery)return;
    if(state.document?.document.provenance.last_operation_id && state.document.document.dirty_stages.length){
      set({errorMessage:'Working-document operations require explicit Recompute support before Publish. Save preserves these edits.'});return;
    }
    if(state.document && (state.hasUnsavedChanges || Object.keys(state.editorTransforms).length ||
      JSON.stringify(state.schematicData)!==JSON.stringify(documentSchematicGraph(state.document)) ||
      Object.entries(overrides||{}).some(([key,value])=>JSON.stringify(value)!==JSON.stringify(state.requirementValues[key])))){
      set({errorMessage:'Save input drafts before Publish. Placement and schematic overlays cannot be published by the current automatic pipeline; reset those drafts before publishing.'});return;
    }
    const token = projectRequest;
    set({ isGenerating: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const result = await generateDesign(state.projectId, { ...state.requirementValues, ...overrides }, state.lockVersion, state.projectConfiguration);
      const [project, revisions, document] = await Promise.all([fetchProject(state.projectId), fetchRevisions(state.projectId),
        state.document ? fetchDocument(state.projectId) : Promise.resolve(null)]);
      if (token !== projectRequest) return;
      const recovery=checkpointAfterGeneration(state,get());
      set({ ...projectFields(project), ...designFields(result), ...(document?documentFields(document):{}), revisions, isGenerating: false, ...recovery });
    } catch (error) {
      if (token === projectRequest) set({ isGenerating: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  applyChangePropagation: async (field, newValue) => {
    if(get().viewedRevisionId)return;
    if(get().document){set({errorMessage:'Save the complete draft, then use Publish to recompute and publish its inputs.'});return;}
    const state = get();
    if(state.isSaving||state.isGenerating||state.pendingRecovery)return;
    const token=projectRequest;
    const otherEdits = Object.keys(state.requirementValues).some((key) => key !== field &&
      JSON.stringify(state.requirementValues[key]) !== JSON.stringify(state.savedRequirementValues[key]));
    if (otherEdits || JSON.stringify(state.projectConfiguration) !== JSON.stringify(state.savedConfiguration)) {
      set({ errorMessage: 'Save other requirement and enclosure edits before reviewing a single change.' }); return;
    }
    set({ isGenerating: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const { new_design, diff_report } = await propagateChange(state.projectId, field, newValue, state.lockVersion);
      const [project, revisions] = await Promise.all([fetchProject(state.projectId), fetchRevisions(state.projectId)]);
      if(token!==projectRequest)return;
      const recovery=checkpointAfterGeneration(state,get());
      set({ ...projectFields(project), ...designFields(new_design), revisions, diffReport: diff_report, isDiffModalOpen: true, isGenerating: false, ...recovery });
    } catch (error) {
      if(token===projectRequest)set({ isGenerating: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  refreshCadPreview: async () => {
    if(get().viewedRevisionId)return;
    const state = get();
    if (state.hasUnsavedChanges || state.designStale) { set({ errorMessage: 'Generate the current design before refreshing its preview.' }); return; }
    const token = projectRequest;
    set({ cadJobStatus: 'PENDING', errorMessage: null });
    try {
      const job = await startCadJob(state.projectId, state.lockVersion);
      for (let attempt = 0; attempt < 60; attempt++) {
        if (token !== projectRequest) return;
        const status = await fetchCadJob(state.projectId, job.id);
        if(token!==projectRequest)return;
        if (status.status !== 'PENDING') {
          if (status.status !== 'READY') throw new Error(status.error?.message || 'CAD preview generation failed.');
          set({ artifacts: [status, ...get().artifacts.filter((a) => a.id !== status.id)], cadJobStatus: 'READY' });
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      throw new Error('Preview generation is still pending. Reopen the project to check its saved status.');
    } catch (error) {
      if(token===projectRequest)set({ cadJobStatus: 'FAILED', errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
}));

// Compatibility facade for existing viewers; engineering entities remain in the
// document/project stores and selection contains only their persistent ID.
useSelectionStore.subscribe(selection => {
  const state = useProjectStore.getState();
  const id = engineeringId(selection.selectedId, state);
  if (selection.selectedId !== id) { useSelectionStore.getState().select(id); return; }
  if (state.selectedObjectId !== id) useProjectStore.setState({selectedObjectId: id});
});
useProjectStore.subscribe((state, previous) => {
  if (state.projectId !== previous.projectId || state.document !== previous.document ||
      state.editSequence !== previous.editSequence || state.viewedRevisionId !== previous.viewedRevisionId ||
      state.lockVersion !== previous.lockVersion || state.isLoadingProject !== previous.isLoadingProject ||
      state.isSaving !== previous.isSaving || state.isGenerating !== previous.isGenerating ||
      state.pendingRecovery !== previous.pendingRecovery)
    useCommandStore.getState().cancel();
  if (state.projectId !== previous.projectId) useSelectionStore.getState().select(null);
  else if (state.selectedObjectId !== previous.selectedObjectId)
    useSelectionStore.getState().select(engineeringId(state.selectedObjectId, state));
});

export function recoveryDocument(state: ProjectState): RecoveryDocument {
  return {schema_version:2,baseDocument:state.recoveryBaseDocument,
    requirements:state.requirementValues,configuration:state.projectConfiguration,
    workspace:{editorTransforms:state.editorTransforms,schematicData:state.schematicData},baseRevisionId:state.currentRevisionId};
}
