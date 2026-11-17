"""Defence against accidental mutation through the application's SQLAlchemy engine.

These guards are not database authorization: deployment roles must independently
deny direct SQL mutation of published content. Migration/admin engines are separate.
"""
from sqlalchemy import Delete, Insert, Update, event, select
from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate

from app.persistence import models as m
from app.persistence.repositories import PersistenceError

# Every other mapped table is append-only through this engine, including catalog
# children, projections and referenced working-document snapshots.
MUTABLE_TABLES = frozenset({'projects', 'design_documents', 'project_requirements',
                            'requirement_sources', 'generated_artifacts', 'document_stage_states', 'jobs'})
IMMUTABLE_TABLES = frozenset(m.metadata.tables) - MUTABLE_TABLES
JOB_FIELDS = frozenset({'storage_backend', 'storage_key', 'sha256', 'byte_size',
                       'generation_status', 'completed_at', 'error'})
EXECUTION_FIELDS = frozenset({'state', 'attempts', 'lease_owner', 'lease_token',
                             'lease_expires_at', 'result', 'error', 'updated_at',
                             'started_at', 'completed_at'})


def immutable():
    return PersistenceError('IMMUTABLE_PUBLICATION',
        'Published content cannot be changed or deleted. Publish a new revision or version.', 409)


def guard_publications(conn, statement, multiparams, params, execution_options):
    if not isinstance(statement, (Update, Delete, Insert)):
        return
    table = statement.table
    if table.name not in m.metadata.tables:
        return
    if isinstance(statement, Insert):
        if isinstance(getattr(statement, '_post_values_clause', None), OnConflictDoUpdate):
            # No supported path needs an upsert that overwrites an existing row.
            raise immutable()
        return
    if table.name in IMMUTABLE_TABLES or (
            isinstance(statement, Delete) and table.name not in {'project_requirements', 'requirement_sources'}):
        raise immutable()
    if table.name in {'projects', 'design_documents', 'document_stage_states'}:
        return
    if table.name == 'jobs':
        keys = {getattr(key, 'name', key) for key in (statement._values or {})}
        if not keys or not keys <= EXECUTION_FIELDS:
            raise immutable()
        return
    if table.name == 'generated_artifacts':
        keys = {getattr(key, 'name', key) for key in (statement._values or {})}
        if not keys or not keys <= JOB_FIELDS:
            raise immutable()
    # Lock matched rows before inspecting their publication state. This also
    # serializes concurrent job completions; READY/FAILED can never be reset.
    query = select(table).where(*statement._where_criteria).with_for_update()
    parameter_sets = multiparams or [params]
    for parameters in parameter_sets:
        for row in conn.execute(query, parameters).mappings():
            if table.name == 'generated_artifacts':
                if row['generation_status'] != 'PENDING':
                    raise immutable()
            elif table.name == 'project_requirements':
                if row['project_revision_id'] is not None:
                    raise immutable()
            else:
                revision = conn.scalar(select(m.project_requirements.c.project_revision_id).where(
                    m.project_requirements.c.id == row['requirement_id']))
                if revision is not None:
                    raise immutable()


def install_publication_guards(engine):
    event.listen(engine, 'before_execute', guard_publications)
