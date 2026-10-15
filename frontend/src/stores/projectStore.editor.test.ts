import { describe, expect, it } from 'vitest';
import { useProjectStore } from './projectStore';

describe('3D editor transform history', () => {
  it('supports undo and redo for a numerical transform edit', () => {
    useProjectStore.setState({
      pdm: { components: [{ cem_component_id: 'QF001', position: { x: 10, y: 20, z: 30 }, rotation_deg: 0 }] } as any,
      editorTransforms: {}, editorUndoStack: [], editorRedoStack: [], pendingEditorEdit: null,
    });

    useProjectStore.getState().updateEditorTransform('QF001', { x: 25 });
    useProjectStore.getState().commitEditorTransform();
    expect(useProjectStore.getState().editorTransforms.QF001.x).toBe(25);

    useProjectStore.getState().undoEditorTransform();
    expect(useProjectStore.getState().editorTransforms).toEqual({});

    useProjectStore.getState().redoEditorTransform();
    expect(useProjectStore.getState().editorTransforms.QF001.x).toBe(25);
  });
});
