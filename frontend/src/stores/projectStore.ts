import { create } from 'zustand';
import { CanonicalEngineeringModel } from '../types/cem';
import { PhysicalDesignModel } from '../types/pdm';
import { generateDesign, propagateChange } from '../api/client';

export type ViewTab = 'requirements' | 'schematic' | 'layout2d' | 'threeD' | 'validation' | 'bom';

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
  schematicData: any | null;
  cadData: any | null;
  
  diffReport: any | null;
  isDiffModalOpen: boolean;
  isGenerating: boolean;
  
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
  schematicData: null,
  cadData: null,
  diffReport: null,
  isDiffModalOpen: false,
  isGenerating: false,
  
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
  
  runDesignPipeline: async (overrides) => {
    set({ isGenerating: true });
    try {
      const pid = get().projectId;
      const values = overrides || get().requirementValues;
      const result = await generateDesign(pid, values);
      set({
        cem: result.cem,
        pdm: result.pdm,
        schematicData: result.schematic,
        cadData: result.cad,
        isGenerating: false,
      });
    } catch (err) {
      console.error(err);
      set({ isGenerating: false });
    }
  },
  
  applyChangePropagation: async (field, newValue) => {
    set({ isGenerating: true });
    try {
      const pid = get().projectId;
      const { new_design, diff_report } = await propagateChange(pid, field, newValue);
      set((state) => ({
        requirementValues: { ...state.requirementValues, [field]: newValue },
        cem: new_design.cem,
        pdm: new_design.pdm,
        schematicData: new_design.schematic,
        cadData: new_design.cad,
        diffReport: diff_report,
        isDiffModalOpen: true,
        isGenerating: false,
      }));
    } catch (err) {
      console.error(err);
      set({ isGenerating: false });
    }
  },
}));
