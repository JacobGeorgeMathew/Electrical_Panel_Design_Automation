import type { ValidationViolation } from './pdm';

export type ValidationStatus = 'PASS' | 'FAIL' | 'UNRESOLVED' | 'NOT_APPLICABLE';
export type ValidationApplicability = 'APPLICABLE' | 'UNKNOWN' | 'NOT_APPLICABLE';
export type ValidationDomain = 'REQUIREMENT' | 'ELECTRICAL' | 'PHYSICAL' | 'THERMAL_SCREEN' | 'GEOMETRY';
export type ValidationSeverity = 'CRITICAL' | 'WARNING' | 'INFO';

export interface ValidationRule {
  id: string;
  object_id: string;
  object_kind: string;
  domain: ValidationDomain;
  purpose: 'PROTOTYPE' | 'ENGINEERING';
  rule_id: string;
  rule_version: string;
  severity: ValidationSeverity;
  required: boolean;
  applicability: ValidationApplicability;
  applicability_rationale: string | null;
}

export interface ValidationResult {
  rule: ValidationRule;
  status: ValidationStatus;
  message: string;
  evidence: string[];
  current: boolean;
  actual_value: number | null;
  required_value: number | null;
  unit: string | null;
}

export interface ValidationGroup {
  object_id: string;
  object_kind: string;
  domain: ValidationDomain;
  rule_id: string;
  rule_version: string;
  severity: ValidationSeverity;
  applicability: ValidationApplicability;
  check_ids: string[];
  status: ValidationStatus;
}

export interface ValidationReport {
  schema_version: 'aggregate-validation/1';
  project_id: string;
  panel_id: string;
  revision_id: string | null;
  checks: ValidationResult[];
  physical_evaluated: boolean;
  physical_violation_count: number;
  engineering_policy_review_reference: string | null;
  groups: ValidationGroup[];
  required_status: ValidationStatus;
  engineering_status: ValidationStatus;
  geometric_feasible: boolean;
  physical_generation_eligible: boolean;
  prototype_preview_available: boolean;
  engineering_release_eligible: boolean;
  blocking_check_ids: string[];
}

export interface ProjectValidationResponse {
  project_id: string;
  revision_id: string;
  violations: ValidationViolation[];
  results: Record<string, unknown>[];
  thermal_density_index: number;
  total_heat_loss_watts: number;
  aggregate: ValidationReport;
}
