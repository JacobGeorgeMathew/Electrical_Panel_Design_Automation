"""Bounded engineering draft edits. No generation or publication occurs here.

Runtime callers materialize server-owned catalog choices while reading the base,
then close the transaction before evaluating the detached candidate. Catalog
version IDs remain in the immutable operation payload; generated base pins are
retained until explicit recomputation. No caller-supplied catalog rows are trusted
by the HTTP or persistence boundaries.
"""
from dataclasses import dataclass, field

from sqlalchemy import select

from app.models.cem import ComponentRef
from app.models.pdm import EnclosureSpec
from app.models.requirements import QuestionSchema, RequirementState
from app.persistence import models as m
from app.persistence.repositories import CatalogRepository, identifier
from app.services.design_errors import DesignError
from app.services.requirement_engine import RequirementEngine


def reject(op, code, message):
    raise DesignError(code, message, {'operation_id': str(op.operation_id)})


@dataclass(frozen=True)
class EngineeringChoices:
    questions: tuple[QuestionSchema, ...] = ()
    # Keyed by exact published version, not latest catalog identity.
    components: dict[str, dict] = field(default_factory=dict)
    products: frozenset[tuple[str, str]] = frozenset()


def load_choices(session, assets, base, request, archetype_version_id=None):
    """Read exact versions and the pinned questionnaire; never write catalogs."""
    catalog = CatalogRepository(session, assets)
    questions = ()
    if any(op.type == 'UpdateRequirement' for op in request.operations):
        version = base.document.pins.catalog_versions.get('archetype') or archetype_version_id
        if version is None:
            raise DesignError('OPERATION_CATALOG', 'A pinned questionnaire is required.', {})
        template = catalog.template(base.document.archetype, version_id=version)
        questions = tuple(QuestionSchema.model_validate(q) for q in template['questions'])
    choices, products = {}, set()
    for op in request.operations:
        if op.type not in ('ChangeComponentRating', 'ResizeEnclosure', 'AddComponent'):
            continue
        version = op.parameters.component_version_id
        c, v = m.components, m.component_versions
        row = session.execute(select(c.c.id.label('component_id'), c.c.code, c.c.name,
            c.c.category_code, c.c.component_kind, v).join(v, c.c.id == v.c.component_id)
            .where(v.c.id == identifier(version), v.c.status == 'PUBLISHED')).mappings().first()
        if row is not None:
            choices[version] = catalog._component(row)
        if op.type == 'AddComponent' and op.parameters.product_version_id is not None:
            product = session.scalar(select(m.product_versions.c.id).where(
                m.product_versions.c.id == identifier(op.parameters.product_version_id),
                m.product_versions.c.component_version_id == identifier(version),
                m.product_versions.c.status == 'PUBLISHED'))
            if product is not None:
                products.add((version, str(product)))
    return EngineeringChoices(questions, choices, frozenset(products))


def update_requirement(candidate, op, choices):
    requirements = candidate.snapshots.requirements
    item = next((r for r in requirements.items if r.id == op.target.requirement_id), None)
    question = next((q for q in choices.questions if q.id == op.target.requirement_id), None)
    if item is None or question is None:
        reject(op, 'OPERATION_TARGET', 'Requirement must exist in the document and permitted questionnaire.')
    values = {r.id: r.value for r in requirements.items}
    values[item.id] = op.parameters.value
    # Use the existing rules without loading JSON fixture templates. Only inspect
    # this field: an incomplete draft may legitimately have other missing inputs.
    engine = RequirementEngine(templates={requirements.archetype:
        {'questions': [q.model_dump() for q in choices.questions]}})
    evaluated = engine.validate_requirements(requirements.project_id, requirements.archetype, values)
    checked = next(r for r in evaluated.items if r.id == item.id)
    if checked.state in (RequirementState.CONFLICTING, RequirementState.MISSING) or checked.source == 'SYSTEM':
        reject(op, 'OPERATION_REQUIREMENT', 'Requirement value is unsupported or not applicable.')
    if item.value == op.parameters.value:
        return []
    # Preserve ID, label and unit, and all other requirements' provenance. The
    # original source/value remain available in retained before snapshots/history.
    desired = dict(value=op.parameters.value, state=RequirementState.PROPOSED,
                   source=op.origin.kind if op.origin.kind != 'MANUAL' else 'USER', message=None)
    fields = [key for key, value in desired.items() if getattr(item, key) != value
              or (key == 'value' and type(item.value) is not type(value))]
    for key, value in desired.items():
        setattr(item, key, value)
    requirements.is_valid = False
    requirements.validation_errors = []
    requirements.validation_warnings = []
    return fields + ['validation']


def catalog_choice(op, choices):
    row = choices.components.get(op.parameters.component_version_id)
    if row is None or row['code'] != op.parameters.catalog_id:
        reject(op, 'OPERATION_CATALOG', 'An exact published catalog choice is required.')
    return row


def change_component_rating(candidate, op, choices):
    cem = candidate.snapshots.cem
    component = next((c for c in cem.components if c.id == op.target.cem_component_id), None)
    if component is None:
        reject(op, 'OPERATION_TARGET', 'Electrical component must already exist.')
    row = catalog_choice(op, choices)
    if (row['current_rating'] != op.parameters.current_rating
            or row['category'] != component.category or row['poles'] != component.poles
            or row['mounting'] != component.mounting
            or row['breaking_capacity'] < component.breaking_capacity
            or {t['id'] for t in row['terminals']} != {t['id'] for t in component.terminals}):
        reject(op, 'OPERATION_CATALOG', 'Rating substitution must preserve category, poles, mounting and terminals without reducing breaking capacity.')
    # Replace only catalog-owned fields; logical identity, quantity, connections,
    # nets, physical placement and schematic presentation remain intact and dirty.
    values = {key: row[key] for key in ('name', 'category', 'current_rating', 'breaking_capacity',
        'poles', 'width', 'height', 'depth', 'mounting', 'heat_loss', 'cad_model', 'terminals',
        'component_version_id', 'product_version_id')}
    values.update(catalog_id=row['code'], cad_model_version_id=None)
    replacement = ComponentRef.model_validate({**component.model_dump(), **values})
    if replacement == component:
        return []
    cem.components[cem.components.index(component)] = replacement
    return ['component_catalog']


def resize_enclosure(candidate, op, choices):
    pdm = candidate.snapshots.pdm
    if pdm.enclosure_id != op.target.enclosure_id:
        reject(op, 'OPERATION_TARGET', 'Enclosure must match the current physical document.')
    row = catalog_choice(op, choices)
    if row['category'] != 'ENCLOSURE' or any(row[axis] != getattr(op.parameters, axis)
                                           for axis in ('width', 'height', 'depth')):
        reject(op, 'OPERATION_CATALOG', 'Dimensions must exactly match a published enclosure.')
    spec = EnclosureSpec.model_validate({**row['specification'], **row, 'id': row['code']})
    values = dict(enclosure_id=spec.id, enclosure_width=spec.width, enclosure_height=spec.height,
        enclosure_depth=spec.depth, ip_rating=spec.ip_rating,
        mounting_plate_x=spec.mounting_plate_offset_x, mounting_plate_y=spec.mounting_plate_offset_y,
        mounting_plate_z=spec.mounting_plate_offset_z)
    if all(getattr(pdm, key) == value for key, value in values.items()):
        return []
    for key, value in values.items():
        setattr(pdm, key, value)
    # Existing zones, rails, devices and routes are retained as stale outputs;
    # moving them here would silently perform placement/routing.
    return ['enclosure_catalog']
