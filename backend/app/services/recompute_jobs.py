"""Document-scoped recompute queue operations and safe progress projections."""
from sqlalchemy import select

from app.jobs.runner import signature
from app.persistence import models as m
from app.persistence.documents import DocumentRepository, document_hash
from app.persistence.jobs import JobRepository
from app.persistence.repositories import ProjectRepository, PersistenceError
from app.services.recompute import check_base


def public_job(session, row):
    result = row['result']
    if row['state'] != 'SUCCEEDED':
        # The frozen jobs schema reserves result for successful completion.
        # Derive live progress from this parent's durable stage attempts.
        from app.services.stages.cache import ADAPTERS
        stages = session.execute(select(m.jobs).where(m.jobs.c.kind == 'STAGE',
            m.jobs.c.document_id == row['document_id'],
            m.jobs.c.execution_key.endswith(f':{row["id"]}:{row["attempts"]}'))
            .order_by(m.jobs.c.created_at)).mappings().all()
        records = []
        for stage in stages:
            name = stage['inputs']['adapter']
            if stage['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
                records.append(dict(stage_id=ADAPTERS[name].stage_id, adapter=name,
                    status='EXECUTED' if stage['state'] == 'SUCCEEDED' else 'FAILED',
                    executions=1, elapsed_ms=max(0, (stage['completed_at'] - (stage['started_at'] or stage['created_at'])).total_seconds()*1000),
                    input_signature=stage['inputs']['stage_signature'],
                    failure_code=stage['error']['code'] if stage['error'] else None))
        result = {'current_stage': next((s['inputs']['adapter'] for s in stages if s['state'] == 'RUNNING'), None),
                  'stage_executions': records}
    return {**{key: row[key] for key in ('id', 'document_id', 'base_sequence', 'state',
        'attempts', 'max_attempts', 'error', 'created_at', 'updated_at')}, 'result': result,
        'base_version': row['inputs']['request']['expected_version'],
        'base_sha256': row['inputs']['document_sha256']}


def owned_job(session, project_id, job_id):
    project = ProjectRepository(session).row(project_id)
    row = JobRepository(session).get(job_id)
    if row['project_id'] != project['id'] or row['kind'] != 'RECOMPUTE':
        raise PersistenceError('JOB_NOT_FOUND', 'Job was not found in this project.', 404)
    return row


def submit(database, project_id, data, idempotency_key):
    with database.sessions.begin() as session:
        project = ProjectRepository(session).row(project_id, lock=True)
        repo = JobRepository(session)
        execution_key = f'recompute:{project["id"]}:{idempotency_key}'
        # An acknowledgement lost in transit can be recovered even after the
        # document advances. Reusing the key for different intent is rejected.
        existing = session.execute(select(m.jobs).where(m.jobs.c.execution_key == execution_key)).mappings().first()
        if existing:
            if existing['inputs']['request'] != data.model_dump(mode='json'):
                raise PersistenceError('JOB_EXECUTION_CONFLICT', 'Job key identifies different intent.', 409)
            return public_job(session, existing)
        source = DocumentRepository(session).load(project)
        check_base(source, data)
        inputs = dict(request=data.model_dump(mode='json'), document_sha256=document_hash(source.document))
        intent = {'kind': 'RECOMPUTE'}
        return public_job(session, repo.enqueue(execution_key=execution_key, project_id=project['id'],
            document_id=data.document_id, base_sequence=data.expected_document_sequence,
            kind='RECOMPUTE', inputs=inputs, artifact_intent=intent,
            input_signature=signature(inputs, intent)))


def recent(database, project_id):
    with database.sessions() as session:
        project = ProjectRepository(session).row(project_id)
        rows = session.execute(select(m.jobs).where(m.jobs.c.project_id == project['id'],
            m.jobs.c.kind == 'RECOMPUTE').order_by(m.jobs.c.created_at.desc()).limit(20)).mappings()
        return [public_job(session, row) for row in rows]


def status(database, project_id, job_id):
    with database.sessions() as session:
        return public_job(session, owned_job(session, project_id, job_id))


def cancel(database, project_id, job_id):
    with database.sessions.begin() as session:
        job = owned_job(session, project_id, job_id)
        repo = JobRepository(session)
        row = repo.cancel(job_id)
        if row['state'] == 'CANCELLED':
            children = list(session.scalars(select(m.jobs.c.id).where(m.jobs.c.kind == 'STAGE',
                m.jobs.c.document_id == job['document_id'],
                m.jobs.c.execution_key.endswith(f':{job["id"]}:{job["attempts"]}'))))
            for child in children:
                repo.cancel(child)
        return public_job(session, row)
