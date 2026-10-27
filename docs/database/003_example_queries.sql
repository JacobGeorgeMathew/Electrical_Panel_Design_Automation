-- Bind :name placeholders using SQLAlchemy text() or an equivalent parameter API.

-- 1. Components in a category, with their latest published specification.
SELECT c.id, c.code, c.name, cv.id AS component_version_id, cv.version_no,
       cv.rated_current_a, cv.rated_voltage_v, cv.width_mm, cv.height_mm, cv.depth_mm
FROM components c
JOIN LATERAL (
  SELECT * FROM component_versions v WHERE v.component_id=c.id AND v.status='PUBLISHED'
  ORDER BY v.version_no DESC LIMIT 1
) cv ON true
WHERE c.category_code=:category_code
ORDER BY c.code;

-- 2. Products meeting required ratings. Use explicit nullable requirement parameters.
SELECT p.id AS product_id, p.manufacturer_sku, p.display_name, pv.id AS product_version_id,
       cv.id AS component_version_id, cv.rated_current_a, cv.rated_voltage_v, cv.breaking_capacity_ka, cv.pole_count
FROM products p JOIN product_versions pv ON pv.product_id=p.id
JOIN component_versions cv ON cv.id=pv.component_version_id
JOIN components c ON c.id=cv.component_id
WHERE c.category_code=:category_code AND pv.status='PUBLISHED' AND cv.status='PUBLISHED'
  AND (CAST(:min_current_a AS numeric) IS NULL OR cv.rated_current_a >= CAST(:min_current_a AS numeric))
  AND (CAST(:min_voltage_v AS numeric) IS NULL OR cv.rated_voltage_v >= CAST(:min_voltage_v AS numeric))
  AND (CAST(:min_breaking_ka AS numeric) IS NULL OR cv.breaking_capacity_ka >= CAST(:min_breaking_ka AS numeric))
  AND (CAST(:pole_count AS smallint) IS NULL OR cv.pole_count = CAST(:pole_count AS smallint))
ORDER BY cv.rated_current_a, p.manufacturer_sku;

-- 3. CAD model versions available for a component version.
SELECT cm.id, cm.code, cm.name, cmv.id AS cad_model_version_id, cmv.version_no, cmv.status, ccm.representation_role
FROM component_cad_models ccm JOIN cad_model_versions cmv ON cmv.id=ccm.cad_model_version_id
JOIN cad_models cm ON cm.id=cmv.cad_model_id
WHERE ccm.component_version_id=:component_version_id AND cmv.status='PUBLISHED';

-- 4. Assets for one CAD model version.
SELECT id, asset_role, file_format, storage_backend, storage_key, sha256, byte_size, generation_status
FROM cad_assets WHERE cad_model_version_id=:cad_model_version_id ORDER BY asset_role, created_at;

-- 5. Compatible accessories for a version (the compatible target is a component version).
SELECT c.id, c.code, c.name, cv.id AS accessory_version_id, ca.relation_code, ca.constraints
FROM component_accessories ca JOIN component_versions cv ON cv.id=ca.accessory_component_version_id
JOIN components c ON c.id=cv.component_id
WHERE ca.component_version_id=:component_version_id AND ca.relation_code='COMPATIBLE' AND cv.status='PUBLISHED';

-- 6. Component roles required by an archetype version and their constraints.
SELECT fm.code AS module_code, mrr.role_code, mrr.quantity_min, mrr.quantity_max,
       mrr.required_properties, mrr.selection_policy
FROM archetype_modules am JOIN functional_module_versions fmv ON fmv.id=am.module_version_id
JOIN functional_modules fm ON fm.id=fmv.module_id
JOIN module_role_requirements mrr ON mrr.module_version_id=fmv.id
WHERE am.archetype_version_id=:archetype_version_id ORDER BY am.sequence_no, mrr.role_code;

-- 7. Connection template with role and terminal codes.
SELECT tc.connection_code, tc.connection_type, tc.directionality,
       from_role.role_code AS from_role, from_term.terminal_code AS from_terminal,
       to_role.role_code AS to_role, to_term.terminal_code AS to_terminal
FROM template_connections tc
JOIN template_terminals from_term ON from_term.id=tc.from_template_terminal_id
JOIN template_component_roles from_role ON from_role.id=from_term.template_role_id
JOIN template_terminals to_term ON to_term.id=tc.to_template_terminal_id
JOIN template_component_roles to_role ON to_role.id=to_term.template_role_id
WHERE tc.template_version_id=:template_version_id ORDER BY tc.connection_code;

-- 8. Questionnaire in display order with options; questions without options remain.
SELECT s.sequence_no AS section_order, q.sequence_no AS question_order, s.code AS section_code,
       q.code, q.prompt, q.value_type, q.unit_code, q.required, q.validation,
       qo.option_code, qo.label, qo.value, qo.sequence_no AS option_order
FROM questions q LEFT JOIN questionnaire_sections s ON s.id=q.section_id
LEFT JOIN question_options qo ON qo.question_id=q.id
WHERE q.questionnaire_version_id=:questionnaire_version_id
ORDER BY COALESCE(s.sequence_no,0), q.sequence_no, qo.sequence_no;

-- 9. Example answer-to-requirement projection. Mapping is application-owned and explicit.
-- This SELECT returns validated candidates; the service inserts requirements and sources
-- in the same transaction after applying the mapping/unit conversion policy.
SELECT qa.id AS answer_id, q.code AS question_code, q.value_type,
       qa.answer_value, q.unit_code AS answer_unit,
       CASE q.code WHEN 'system_voltage' THEN 'system_voltage' END AS requirement_code,
       CASE q.code WHEN 'system_voltage' THEN 'EQ' END AS requirement_operator,
       jsonb_build_object('value',qa.answer_value->'value') AS requirement_value
FROM question_answers qa JOIN questions q ON q.id=qa.question_id
WHERE qa.session_id=:session_id AND q.code IN ('system_voltage');

-- 10. Latest immutable revision for one project.
SELECT * FROM project_revisions WHERE project_id=:project_id ORDER BY revision_no DESC LIMIT 1;

-- 11. Restore/reopen both canonical snapshots for a selected historical revision.
SELECT r.id AS revision_id, r.revision_no, r.model_manifest, cem.snapshot AS cem_snapshot,
       cem.sha256 AS cem_sha256, pdm.snapshot AS pdm_snapshot, pdm.sha256 AS pdm_sha256
FROM project_revisions r JOIN cem_snapshots cem ON cem.project_revision_id=r.id
LEFT JOIN pdm_snapshots pdm ON pdm.project_revision_id=r.id
WHERE r.id=:project_revision_id;

-- 12. Physical placements and corresponding logical CEM components.
SELECT pdi.stable_key AS physical_key, ci.stable_key AS cem_key, ci.role_code,
       pdi.cad_model_version_id, pl.transform, pl.bounding_box_mm, pl.zone_code, ms.stable_key AS mount_key
FROM pdm_component_instances pdi JOIN cem_component_instances ci ON ci.id=pdi.cem_component_instance_id
LEFT JOIN pdm_placements pl ON pl.pdm_component_instance_id=pdi.id
LEFT JOIN pdm_mounting_structures ms ON ms.id=pl.mounting_structure_id
WHERE pdi.project_revision_id=:project_revision_id ORDER BY pdi.stable_key;

-- 13. Projects whose revisions selected a specified catalog component version.
SELECT DISTINCT p.id, p.project_code, p.name
FROM projects p JOIN project_revisions r ON r.project_id=p.id
LEFT JOIN revision_components rc ON rc.project_revision_id=r.id
LEFT JOIN cem_component_instances ci ON ci.project_revision_id=r.id
WHERE rc.component_version_id=:component_version_id OR ci.component_version_id=:component_version_id
ORDER BY p.name;

-- 14. Latest artifact of a chosen type from a revision.
SELECT * FROM generated_artifacts WHERE project_revision_id=:project_revision_id
  AND artifact_type=:artifact_type ORDER BY created_at DESC LIMIT 1;

-- 15. Rule versions pinned by revision and their latest validation results.
SELECT rs.code AS rule_set_code, rs.version_no AS rule_set_version, dr.code AS rule_code,
       drv.version_no AS rule_version, vr.result_status, vr.message, vr.affected_entities,
       vr.measured_values, vr.evidence
FROM project_revisions pr JOIN rule_set_versions rsv ON rsv.id=pr.rule_set_version_id
JOIN rule_sets rs ON rs.id=rsv.rule_set_id
JOIN rule_set_members rsm ON rsm.rule_set_version_id=rsv.id
JOIN design_rule_versions drv ON drv.id=rsm.rule_version_id
JOIN design_rules dr ON dr.id=drv.rule_id
LEFT JOIN LATERAL (
  SELECT vr.* FROM validation_runs run JOIN validation_results vr ON vr.validation_run_id=run.id
  WHERE run.project_revision_id=pr.id AND vr.rule_version_id=drv.id
  ORDER BY run.started_at DESC LIMIT 1
) vr ON true
WHERE pr.id=:project_revision_id ORDER BY dr.code;

-- 16. Find reachable downstream outputs from a changed dependency key.
WITH RECURSIVE affected(kind, key, depth, visited) AS (
  SELECT CAST(:source_kind AS text), CAST(:source_key AS text), 0,
         ARRAY[CAST(:source_kind AS text) || ':' || CAST(:source_key AS text)]
  UNION ALL
  SELECT d.target_kind, d.target_key, a.depth+1,
         a.visited || (d.target_kind || ':' || d.target_key)
  FROM affected a JOIN revision_dependencies d
    ON d.project_revision_id=:project_revision_id
   AND d.source_kind=a.kind AND d.source_key=a.key
  WHERE NOT ((d.target_kind || ':' || d.target_key) = ANY(a.visited))
)
SELECT DISTINCT kind, key, min(depth) AS dependency_depth FROM affected
GROUP BY kind, key ORDER BY dependency_depth, kind, key;

-- Mark affected dependencies stale (execute in the revision mutation transaction).
WITH RECURSIVE affected(kind, key, visited) AS (
  SELECT CAST(:source_kind AS text), CAST(:source_key AS text),
         ARRAY[CAST(:source_kind AS text) || ':' || CAST(:source_key AS text)]
  UNION ALL
  SELECT d.target_kind, d.target_key, a.visited || (d.target_kind || ':' || d.target_key)
  FROM affected a JOIN revision_dependencies d
    ON d.project_revision_id=:project_revision_id AND d.source_kind=a.kind AND d.source_key=a.key
  WHERE NOT ((d.target_kind || ':' || d.target_key) = ANY(a.visited))
)
UPDATE revision_dependencies d SET status='STALE'
FROM (SELECT DISTINCT kind, key FROM affected) a
WHERE d.project_revision_id=:project_revision_id
  AND d.target_kind=a.kind AND d.target_key=a.key;
