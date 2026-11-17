import { describe, expect, it } from 'vitest';
import fixture from './fixtures/validation-report-v1.json';
import type { ValidationReport } from './validation';

type JsonShape<T> = T extends string ? string : T extends number ? number
  : T extends (infer Item)[] ? JsonShape<Item>[]
  : T extends object ? { [Key in keyof T]: JsonShape<T[Key]> } : T;
const shared: JsonShape<ValidationReport> = fixture;

describe('aggregate validation contract', () => {
  it('keeps preview feasibility separate from unresolved required engineering', () => {
    expect(shared.schema_version).toBe('aggregate-validation/1');
    expect(shared.geometric_feasible).toBe(true);
    expect(shared.physical_generation_eligible).toBe(true);
    expect(shared.prototype_preview_available).toBe(true);
    expect(shared.engineering_release_eligible).toBe(false);
    expect(shared.blocking_check_ids).toEqual(['check-bend']);
    const bend = shared.checks.find(check => check.rule.id === 'check-bend');
    expect(bend?.rule.required).toBe(true);
    expect(bend?.rule.severity).toBe('WARNING');
    expect(bend?.rule.applicability).toBe('UNKNOWN');
  });

  it('preserves object and version references, group membership and finite mm evidence', () => {
    const ids = new Set(shared.checks.map(check => check.rule.id));
    for (const group of shared.groups) {
      expect(group.object_id).toBe('route-1');
      expect(group.rule_version).toBe('synthetic/1');
      expect(group.check_ids.every(id => ids.has(id))).toBe(true);
    }
    expect(shared.checks[0].unit).toBe('mm');
    expect(Number.isFinite(shared.checks[0].actual_value)).toBe(true);
  });
});
