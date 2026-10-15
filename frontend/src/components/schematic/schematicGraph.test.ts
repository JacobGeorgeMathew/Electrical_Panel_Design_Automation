import { describe, expect, it } from 'vitest';
import { buildSchematicGraph, validateSchematicGraph, type SchematicGraphData } from './schematicGraph';

const graphFixture: SchematicGraphData = {
  width: 400, height: 300,
  symbols: [
    { id: 'QF001', name: 'Incomer', type: 'MCCB', category: 'MCCB', x: 100, y: 20, width: 60, height: 80, label: 'QF001\n250A', terminals: [{ id: 'OUT', x: 130, y: 100 }] },
    { id: 'BUS001', name: 'Busbar', type: 'BUSBAR', category: 'BUSBAR', x: 20, y: 150, width: 240, height: 20, label: 'Main busbar', terminals: [{ id: 'IN', x: 140, y: 150 }] },
    { id: 'QF002', name: 'Feeder A', type: 'MCB', category: 'MCB', x: 300, y: 150, width: 40, height: 60, label: 'QF002', terminals: [{ id: 'IN', x: 320, y: 150 }] },
  ],
  wires: [
    { id: 'CONN-01', net_id: 'NET-L1', net_name: 'L1', from: 'QF001', from_terminal: 'OUT', to: 'BUS001', to_terminal: 'IN', wire_class: 'POWER' },
    { id: 'CONN-02', net_id: 'NET-L1', net_name: 'L1', from: 'BUS001', from_terminal: 'IN', to: 'QF002', to_terminal: 'IN', wire_class: 'POWER' },
  ],
};

describe('schematic graph mapping and rules', () => {
  it('maps stable CEM connection IDs to terminal handles and creates fan-out junctions', () => {
    const result = buildSchematicGraph(graphFixture);
    expect(result.nodes.map((node) => node.id)).toContain('QF001');
    expect(result.nodes.some((node) => node.id === 'JUNCTION:NET-L1')).toBe(true);
    expect(result.edges).toHaveLength(3);
    expect(result.edges[0].sourceHandle).toBe('source:OUT');
    expect(validateSchematicGraph(result.nodes, result.edges)).toEqual([]);

    const fanout = buildSchematicGraph({ ...graphFixture, wires: [
      ...graphFixture.wires,
      { id: 'CONN-03', net_id: 'NET-L1', net_name: 'L1', from: 'QF001', from_terminal: 'OUT', to: 'QF002', to_terminal: 'IN', wire_class: 'POWER' },
    ] });
    expect(fanout.nodes.some((node) => node.id === 'JUNCTION:NET-L1')).toBe(true);
    expect(fanout.edges).toHaveLength(3);
    expect(validateSchematicGraph(fanout.nodes, fanout.edges)).toEqual([]);
    const splitNet = fanout.edges.map((edge, index) => index === 0 ? { ...edge, data: { ...edge.data!, net_id: 'NET-L2' } } : edge);
    expect(validateSchematicGraph(fanout.nodes, splitNet).map((error) => error.code)).toContain('MIXED_NET_JUNCTION');
  });

  it('reports invalid terminal references, missing labels, and mixed-class rule violations', () => {
    const result = buildSchematicGraph(graphFixture);
    const edge = { ...result.edges[0], sourceHandle: 'source:MISSING', data: { ...result.edges[0].data!, net_name: '' } };
    const errors = validateSchematicGraph(result.nodes, [edge]);
    expect(errors.map((error) => error.code)).toContain('MISSING_TERMINAL');
    expect(errors.map((error) => error.code)).toContain('MISSING_NET');
  });
});
