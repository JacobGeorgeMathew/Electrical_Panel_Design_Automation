"""Asynchronous recompute transport; queue operations own their transactions."""
from fastapi import APIRouter, Depends, Header

from app.api.dependencies import get_service
from app.models.recompute import RecomputeRequest
from app.services import recompute_jobs

router = APIRouter(prefix='/api/projects/{project_id}/design/recompute/jobs', tags=['jobs'])


@router.post('', status_code=202)
def submit(project_id: str, data: RecomputeRequest,
           idempotency_key: str = Header(alias='Idempotency-Key', min_length=1, max_length=128),
           service=Depends(get_service)):
    return recompute_jobs.submit(service.db, project_id, data, idempotency_key)


@router.get('')
def recent(project_id: str, service=Depends(get_service)):
    return recompute_jobs.recent(service.db, project_id)


@router.get('/{job_id}')
def status(project_id: str, job_id: str, service=Depends(get_service)):
    return recompute_jobs.status(service.db, project_id, job_id)


@router.post('/{job_id}/cancel')
def cancel(project_id: str, job_id: str, service=Depends(get_service)):
    return recompute_jobs.cancel(service.db, project_id, job_id)
