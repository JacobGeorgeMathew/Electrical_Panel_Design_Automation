import { create } from 'zustand';
import { CanonicalEngineeringModel } from '../types/cem';
import { PhysicalDesignModel } from '../types/pdm';
import { createProject, generateDesign, propagateChange, validatePlacement, validateRequirements,
  listProjects, fetchProject, fetchDesign, fetchRevisions, restoreRevision, updateProject, fetchArchetypes, startCadJob, fetchCadJob, markProjectOpened, saveRecovery } from '../api/client';
import type { Artifact, Archetype, DesignPackage, ProjectConfiguration, ProjectRecord, RevisionSummary } from '../types/api';

import { readRecovery, clearRecovery, type Checkpoint, type RecoveryDocument } from './projectRecovery';

let projectRequest = 0;
let routingRequest = 0;
let openController: AbortController | null = null;

export type ViewTab = 'requirements' | 'schematic' | 'layout2d' | 'threeD' | 'validation' | 'bom' | 'catalog' | 'documentation';
export type EditorTransform = { x: number; y: number; z: number; rotation_deg: number };
type EditorTransformSnapshot = Record<string, EditorTransform>;
export type EditorMode = 'select' | 'translate' | 'rotate';

interface ProjectState {
  projectDescription: string;
  projectLocation: string;
  recoveryVersion: number;
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

const emptyDesign = { isSaving:false,isGenerating:false,isValidatingPlacement:false, cem: null, pdm: null, pdmBaseline: null, schematicData: null, cadData: null,
  currentRevisionId: null, currentRevisionNo: null, artifacts: [], editorTransforms: {}, editorHiddenComponentIds: [],
  editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null, selectedObjectId: null, hoveredObjectId: null,
  diffReport: null, isDiffModalOpen: false, cadJobStatus: null };
const projectFields = (p: ProjectRecord) => ({ projectId: p.id, projectName: p.name, archetype: p.archetype,
  requirementValues: p.requirements, savedRequirementValues: p.requirements, projectConfiguration: p.configuration,
  savedConfiguration: p.configuration, lockVersion: p.lock_version, hasUnsavedChanges: false,
  projectDescription:p.description || '', projectLocation:p.location || '', recoveryVersion:p.recovery_version || 0, pendingRecovery:null });
const designFields = (d: DesignPackage) => ({ isValidatingPlacement:false, cem: d.cem, pdm: d.pdm, pdmBaseline: d.pdm, schematicData: d.schematic,
  cadData: d.cad, currentRevisionId: d.revision_id, currentRevisionNo: d.revision_no, artifacts: d.artifacts,
  lockVersion: d.lock_version, designStale: d.is_stale, editorTransforms: {}, editorHiddenComponentIds: [],
  editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null });

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectDescription:'', projectLocation:'', recoveryVersion:0, pendingRecovery:null, editSequence:0, autosaveStatus:'',
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
  selectObject: (id) => set(state=>({ selectedObjectId: id===null?null:
    state.pdm?.components.find(c=>c.id===id)?.cem_component_id ||
    state.pdm?.routes.find(r=>r.id===id)?.conductor_id || id })),
  hoverObject: (id) => set({ hoveredObjectId: id }),
  
  setRequirementValue: (field, val) =>
    set((state) => ({
      requirementValues: { ...state.requirementValues, [field]: val },
      hasUnsavedChanges: true, designStale: true, editSequence: state.editSequence+1,
    })),
    
  toggleExplodedView: () => set((state) => ({ explodedView: !state.explodedView })),
  toggleWireVisibility: () => set((state) => ({ wireVisibility: !state.wireVisibility })),
  closeDiffModal: () => set({ isDiffModalOpen: false }),
  clearError: () => set({ errorMessage: null, validationErrors: [], validationWarnings: [] }),
  setError: (message) => set({ errorMessage: message }),
  setEditorMode: (mode) => set({ editorMode: mode }),
  toggleEditorSnap: () => set((state) => ({ editorSnapEnabled: !state.editorSnapEnabled })),
  setEditorGridMm: (gridMm) => set({ editorGridMm: Number.isFinite(gridMm) && gridMm > 0 ? gridMm : 5 }),
  toggleComponentVisibility: (componentId) => set((state) => ({
    editorHiddenComponentIds: state.editorHiddenComponentIds.includes(componentId)
      ? state.editorHiddenComponentIds.filter((id) => id !== componentId)
      : [...state.editorHiddenComponentIds, componentId],
  })),
  updateEditorTransform: (componentId, transform) => set((state) => {
    const component = state.pdm?.components.find((item) => item.cem_component_id === componentId);
    if (!component) return state;
    const base: EditorTransform = {
      x: component.position.x, y: component.position.y, z: component.position.z,
      rotation_deg: component.rotation_deg || 0,
    };
    const current = state.editorTransforms[componentId] || base;
    return {
      hasUnsavedChanges:true, editSequence:state.editSequence+1,
      pdm: state.pdm ? {...state.pdm,routes:[]} : null,
      pendingEditorEdit: state.pendingEditorEdit || { ...state.editorTransforms },
      editorTransforms: { ...state.editorTransforms, [componentId]: { ...current, ...transform } },
    };
  }),
  commitEditorTransform: () => set((state) => {
    if (!state.pendingEditorEdit || JSON.stringify(state.pendingEditorEdit) === JSON.stringify(state.editorTransforms)) {
      return { pendingEditorEdit: null };
    }
    return {
      editorUndoStack: [...state.editorUndoStack, state.pendingEditorEdit].slice(-100),
      editorRedoStack: [],
      pendingEditorEdit: null,
    };
  }),
  undoEditorTransform: () => set((state) => {
    if (!state.editorUndoStack.length) return state;
    return {
      hasUnsavedChanges:true, editSequence:state.editSequence+1,
      editorTransforms: state.editorUndoStack[state.editorUndoStack.length - 1],
      editorUndoStack: state.editorUndoStack.slice(0, -1),
      editorRedoStack: [...state.editorRedoStack, state.editorTransforms],
      pendingEditorEdit: null,
    };
  }),
  redoEditorTransform: () => set((state) => {
    if (!state.editorRedoStack.length) return state;
    return {
      hasUnsavedChanges:true, editSequence:state.editSequence+1,
      editorTransforms: state.editorRedoStack[state.editorRedoStack.length - 1],
      editorRedoStack: state.editorRedoStack.slice(0, -1),
      editorUndoStack: [...state.editorUndoStack, state.editorTransforms],
      pendingEditorEdit: null,
    };
  }),
  resetEditorDraft: () => { routingRequest++;set((state) => ({ isValidatingPlacement:false, hasUnsavedChanges:true,editSequence:state.editSequence+1, pdm: state.pdmBaseline || state.pdm,
    editorTransforms: {}, editorHiddenComponentIds: [], editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null, editorMode: 'select' })); },
  validateCurrentRequirements: async () => {
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
      const [revisions, design] = await Promise.all([
        fetchRevisions(id),
        p.current_revision_id ? fetchDesign(id, signal) : Promise.resolve(null),
      ]);
      if (token !== projectRequest) return;
      set({ ...emptyDesign, ...projectFields(p), ...(design ? designFields(design) : {}),
        revisions, isLoadingProject: false, designStale: design?.is_stale || false,
        validationErrors: [], validationWarnings: [], activeTab: 'requirements',
        editorTransforms:p.workspace?.editorTransforms || {}, schematicData:p.workspace?.schematicData || design?.schematic || null,
        pendingRecovery: [readRecovery(p.id),p.recovery].filter((c):c is Checkpoint=>!!c).sort((a,b)=>b.saved_at.localeCompare(a.saved_at))[0] || null, autosaveStatus:'', editSequence:0 });
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
  setProjectConfiguration: (configuration) => set(state=>({ projectConfiguration: configuration, hasUnsavedChanges: true, designStale: true,editSequence:state.editSequence+1 })),
  setSchematicDraft: (data) => set(state=>({schematicData:data,hasUnsavedChanges:true,editSequence:state.editSequence+1})),
  recoverChanges: () => {
    const state=get(), checkpoint=state.pendingRecovery;
    if(!checkpoint)return;
    const d=checkpoint.document;
    const sameRevision=d.baseRevisionId===state.currentRevisionId;
    set({requirementValues:d.requirements,projectConfiguration:d.configuration,
      ...(sameRevision?{editorTransforms:d.workspace.editorTransforms||{},schematicData:d.workspace.schematicData||state.schematicData}:{}),
      hasUnsavedChanges:true,designStale:true,pendingRecovery:null,editSequence:state.editSequence+1,
      errorMessage:sameRevision?null:'Recovered requirements. Editor changes based on a different revision were not applied.'});
  },
  discardLocalEdits: async () => {
    const state=get(),token=projectRequest;
    if(state.isSaving||state.isGenerating)return;
    set({isSaving:true});
    try{
      await saveRecovery(state.projectId,state.lockVersion,state.recoveryVersion,null);
      if(token!==projectRequest)return;
      clearRecovery(state.projectId);
      set({isSaving:false,hasUnsavedChanges:false});
      await get().openProject(state.projectId,true);
    }catch(error){if(token===projectRequest)set({isSaving:false,errorMessage:error instanceof Error?error.message:String(error)});}
  },
  discardRecovery: async () => {
    const state=get(), token=projectRequest;
    try {
      const p=await saveRecovery(state.projectId,state.lockVersion,state.recoveryVersion,null);
      if(token!==projectRequest)return;
      clearRecovery(state.projectId);
      set({pendingRecovery:null,recoveryVersion:p.recovery_version});
    }catch(error){if(token===projectRequest)set({errorMessage:error instanceof Error?error.message:String(error)});}
  },
  autosave: async () => {
    const state=get(), token=projectRequest;
    if(!state.projectId||!state.hasUnsavedChanges||state.pendingRecovery||state.isSaving||state.isGenerating)return;
    set({isSaving:true,autosaveStatus:'Saving recovery checkpoint…'});
    try{
      const p=await saveRecovery(state.projectId,state.lockVersion,state.recoveryVersion,recoveryDocument(state));
      if(token===projectRequest)set({recoveryVersion:p.recovery_version,isSaving:false,autosaveStatus:'Recovery checkpoint saved'});
    }catch(error){if(token===projectRequest)set({isSaving:false,autosaveStatus:error instanceof Error?error.message:String(error)});}
  },
  saveAndClose: async () => {
    if(get().isSaving||get().isGenerating)return;
    if(get().hasUnsavedChanges)await get().saveCurrentProject();
    if(!get().hasUnsavedChanges)get().closeProject();
  },
  saveCurrentProject: async () => {
    const state=get(), token=projectRequest;
    if(!state.projectId||state.isSaving||state.isGenerating||state.pendingRecovery)return;
    set({isSaving:true,errorMessage:null});
    try {
      const p=await updateProject(state.projectId,state.lockVersion,{
        requirements:state.requirementValues,configuration:state.projectConfiguration,expected_recovery_version:state.recoveryVersion,
        workspace:{editorTransforms:state.editorTransforms,schematicData:state.schematicData},
      });
      if(token!==projectRequest)return;
      const unchanged=get().editSequence===state.editSequence;
      if(unchanged)clearRecovery(state.projectId);
      set({lockVersion:p.lock_version,recoveryVersion:p.recovery_version||0,
        savedRequirementValues:p.requirements,savedConfiguration:p.configuration,
        hasUnsavedChanges:!unchanged,isSaving:false,pendingRecovery:null,autosaveStatus:'Project saved',
        projects:get().projects.map(row=>row.id===p.id?p:row)});
    }catch(error){if(token===projectRequest)set({isSaving:false,errorMessage:error instanceof Error?error.message:String(error)});}
  },
  createNewProject: async (name, archetype = 'DB', versionId, metadata) => {
    set({ isSaving: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const p = await createProject(name, {}, archetype, versionId, metadata);
      ++projectRequest;
      set({ ...emptyDesign, ...projectFields(p), revisions: [], projects: await listProjects(),
        isSaving: false, designStale: false, activeTab: 'requirements',editSequence:0,autosaveStatus:'' });
    } catch (error) {
      set({ isSaving: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  restoreSavedRevision: async (id) => {
    if(get().isSaving||get().isGenerating||get().pendingRecovery)return;
    if (get().hasUnsavedChanges) { set({ errorMessage: 'Save or discard local edits before restoring a revision.' }); return; }
    const state = get();
    const token=projectRequest;
    set({ isSaving: true, errorMessage: null });
    try {
      const result = await restoreRevision(state.projectId, id, state.lockVersion);
      const [project, revisions] = await Promise.all([fetchProject(state.projectId), fetchRevisions(state.projectId)]);
      if(token!==projectRequest)return;
      clearRecovery(state.projectId);
      set({ ...projectFields(project), ...designFields(result), revisions, isSaving: false });
    } catch (error) {
      if(token===projectRequest)set({ isSaving: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  runDesignPipeline: async (overrides) => {
    const state = get();
    if (!state.projectId) { set({ errorMessage: 'Create or open a project before generating a design.' }); return; }
    if(state.isSaving||state.isGenerating||state.pendingRecovery)return;
    const token = projectRequest;
    set({ isGenerating: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const result = await generateDesign(state.projectId, { ...state.requirementValues, ...overrides }, state.lockVersion, state.projectConfiguration);
      const [project, revisions] = await Promise.all([fetchProject(state.projectId), fetchRevisions(state.projectId)]);
      if (token !== projectRequest) return;
      clearRecovery(state.projectId);
      set({ ...projectFields(project), ...designFields(result), revisions, isGenerating: false });
    } catch (error) {
      if (token === projectRequest) set({ isGenerating: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  applyChangePropagation: async (field, newValue) => {
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
      clearRecovery(state.projectId);
      set({ ...projectFields(project), ...designFields(new_design), revisions, diffReport: diff_report, isDiffModalOpen: true, isGenerating: false });
    } catch (error) {
      if(token===projectRequest)set({ isGenerating: false, errorMessage: error instanceof Error ? error.message : String(error) });
    }
  },
  refreshCadPreview: async () => {
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

export function recoveryDocument(state: ProjectState): RecoveryDocument {
  return {requirements:state.requirementValues,configuration:state.projectConfiguration,
    workspace:{editorTransforms:state.editorTransforms,schematicData:state.schematicData},baseRevisionId:state.currentRevisionId};
}
