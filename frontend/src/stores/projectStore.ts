import { create } from 'zustand';
import { CanonicalEngineeringModel } from '../types/cem';
import { PhysicalDesignModel } from '../types/pdm';
import { createProject, generateDesign, propagateChange, validatePlacement, validateRequirements } from '../api/client';

export type ViewTab = 'requirements' | 'schematic' | 'layout2d' | 'threeD' | 'validation' | 'bom';
export type EditorTransform = { x: number; y: number; z: number; rotation_deg: number };
type EditorTransformSnapshot = Record<string, EditorTransform>;
export type EditorMode = 'select' | 'translate' | 'rotate';

interface ProjectState {
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
  createNewProject: (name: string) => Promise<void>;
  
  runDesignPipeline: (overrides?: Record<string, any>) => Promise<void>;
  applyChangePropagation: (field: string, newValue: any) => Promise<void>;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectId: 'PROJ_DB_DEMO_001',
  projectName: 'Main Distribution Panel DB-01',
  archetype: 'DB',
  activeTab: 'requirements',
  selectedObjectId: null,
  hoveredObjectId: null,
  
  requirementValues: {
    supply_voltage: 415,
    phases: 3,
    frequency: 50,
    incomer_rating: 250,
    num_feeders: 12,
    ip_rating: 'IP54',
    spare_capacity_pct: 20,
    neutral_required: true,
  },
  
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
  selectObject: (id) => set({ selectedObjectId: id }),
  hoverObject: (id) => set({ hoveredObjectId: id }),
  
  setRequirementValue: (field, val) =>
    set((state) => ({
      requirementValues: { ...state.requirementValues, [field]: val },
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
      editorTransforms: state.editorUndoStack[state.editorUndoStack.length - 1],
      editorUndoStack: state.editorUndoStack.slice(0, -1),
      editorRedoStack: [...state.editorRedoStack, state.editorTransforms],
      pendingEditorEdit: null,
    };
  }),
  redoEditorTransform: () => set((state) => {
    if (!state.editorRedoStack.length) return state;
    return {
      editorTransforms: state.editorRedoStack[state.editorRedoStack.length - 1],
      editorRedoStack: state.editorRedoStack.slice(0, -1),
      editorUndoStack: [...state.editorUndoStack, state.editorTransforms],
      pendingEditorEdit: null,
    };
  }),
  resetEditorDraft: () => set((state) => ({ pdm: state.pdmBaseline || state.pdm,
    editorTransforms: {}, editorHiddenComponentIds: [], editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null, editorMode: 'select' })),
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
    set({ pdm: updatedPdm, isValidatingPlacement: true, errorMessage: null });
    try {
      const result = await validatePlacement(projectId, updatedPdm);
      set({ pdm: { ...updatedPdm, validation_results: result.validation_results || [] }, isValidatingPlacement: false });
    } catch (err) {
      set({ isValidatingPlacement: false, errorMessage: err instanceof Error ? err.message : String(err) });
    }
  },
  createNewProject: async (name) => {
    set({ isGenerating: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const result = await createProject(name, get().requirementValues);
      set({ projectId: result.id, projectName: result.name, archetype: result.archetype || 'DB',
        cem: null, pdm: null, pdmBaseline: null, schematicData: null, cadData: null, diffReport: null,
        isDiffModalOpen: false, isGenerating: false, validationErrors: [], validationWarnings: [],
        editorTransforms: {}, editorHiddenComponentIds: [], editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null });
      await get().runDesignPipeline();
    } catch (err) {
      set({ isGenerating: false, errorMessage: err instanceof Error ? err.message : String(err) });
    }
  },
  
  runDesignPipeline: async (overrides) => {
    set({ isGenerating: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const pid = get().projectId;
      const values = overrides || get().requirementValues;
      const result = await generateDesign(pid, values);
      set({
        cem: result.cem,
        pdm: result.pdm,
        pdmBaseline: result.pdm,
        schematicData: result.schematic,
        cadData: result.cad,
        isGenerating: false,
        editorTransforms: {}, editorHiddenComponentIds: [], editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null,
      });
    } catch (err) {
      console.error(err);
      set({ isGenerating: false, errorMessage: err instanceof Error ? err.message : String(err) });
    }
  },
  
  applyChangePropagation: async (field, newValue) => {
    set({ isGenerating: true, errorMessage: null, validationErrors: [], validationWarnings: [] });
    try {
      const pid = get().projectId;
      const { new_design, diff_report } = await propagateChange(pid, field, newValue);
      set((state) => ({
        requirementValues: { ...state.requirementValues, [field]: newValue },
        cem: new_design.cem,
        pdm: new_design.pdm,
        pdmBaseline: new_design.pdm,
        schematicData: new_design.schematic,
        cadData: new_design.cad,
        diffReport: diff_report,
        isDiffModalOpen: true,
        isGenerating: false,
        editorTransforms: {}, editorHiddenComponentIds: [], editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null,
      }));
    } catch (err) {
      console.error(err);
      set({ isGenerating: false, errorMessage: err instanceof Error ? err.message : String(err) });
    }
  },
}));
