import {create} from 'zustand';
import type {ProjectState} from './projectStore';

/** Resolve representation IDs without copying engineering entities into UI state. */
export function engineeringId(id: string | null, state: Pick<ProjectState, 'pdm' | 'document'>): string | null {
  if (id === null) return null;
  const snapshots = state.document?.snapshots;
  return state.pdm?.components.find(c => c.id === id)?.cem_component_id
    || snapshots?.pdm?.components.find(c => c.id === id)?.cem_component_id
    || snapshots?.schematic?.symbols.find(s => s.id === id)?.component_id
    || state.pdm?.routes.find(r => r.id === id)?.conductor_id
    || snapshots?.pdm?.routes.find(r => r.id === id)?.conductor_id
    || snapshots?.schematic?.wires.find(w => w.id === id)?.conductor_id
    || snapshots?.schematic?.symbols.flatMap(s => s.pins).find(p => p.id === id)?.terminal_id
    || id;
}

interface SelectionState {
  selectedId: string | null;
  select: (id: string | null) => void;
}
// Only an opaque reference. ProjectStore bridges legacy consumers to this store.
export const useSelectionStore = create<SelectionState>(set => ({
  selectedId: null,
  select: selectedId => set({selectedId}),
}));
