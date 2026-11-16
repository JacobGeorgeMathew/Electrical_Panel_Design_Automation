import {describe,expect,it} from 'vitest';
import {useSelectionStore,engineeringId} from './selectionStore';
import {useProjectStore} from './projectStore';
import fixture from '../types/fixtures/document-v1.json';
import type {DocumentView} from '../types/document';

describe('persistent engineering selection',()=>{
  it('resolves physical, symbol, wire and pin representations to engineering IDs',()=>{
    const view=structuredClone(fixture) as unknown as DocumentView;
    const symbol=view.snapshots.schematic!.symbols[0];
    const wire=view.snapshots.schematic!.wires[0];
    const component=view.snapshots.pdm!.components[0];
    useProjectStore.setState({projectId:'selection-project',document:view,pdm:null});
    const document=useProjectStore.getState().document;
    for(const [representation,expected] of [[component.id,component.cem_component_id],[symbol.id,symbol.component_id],
      [wire.id,wire.conductor_id],[symbol.pins[0].id,symbol.pins[0].terminal_id]]) {
      useProjectStore.getState().selectObject(representation);
      expect(useSelectionStore.getState().selectedId).toBe(expected);
      expect(useProjectStore.getState().selectedObjectId).toBe(expected);
    }
    expect(useProjectStore.getState().document).toBe(document);
    expect(engineeringId('hardware-id',useProjectStore.getState())).toBe('hardware-id');
    useProjectStore.setState({projectId:'different-project'});
    expect(useSelectionStore.getState().selectedId).toBeNull();
  });
  it('normalizes direct shared-store selection for legacy browser/physical/inspector consumers',()=>{
    useProjectStore.setState({pdm:{components:[{id:'physical-Q1',cem_component_id:'Q1'}],routes:[]} as any});
    useSelectionStore.getState().select('physical-Q1');
    expect(useSelectionStore.getState().selectedId).toBe('Q1');
    expect(useProjectStore.getState().selectedObjectId).toBe('Q1');
  });
});
