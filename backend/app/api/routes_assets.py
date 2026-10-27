from fastapi import APIRouter,Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.api.dependencies import get_session,get_service
from app.models.api import ArtifactView
from app.persistence import models as m
from app.persistence.repositories import CatalogRepository,PersistenceError,identifier
from app.persistence.assets import AssetUnavailable

router=APIRouter(prefix='/api',tags=['assets'])

def asset_row(session,asset_id,generated):
    table=m.generated_artifacts if generated else m.cad_assets
    row=session.execute(select(table).where(table.c.id==identifier(asset_id))).mappings().first()
    if row is None: raise PersistenceError('ASSET_NOT_FOUND','Asset was not found.',404)
    return dict(row)

@router.get('/assets/{asset_id}',response_model=ArtifactView)
def asset_metadata(asset_id:str,session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).asset_dto(asset_row(session,asset_id,False))

@router.get('/artifacts/{artifact_id}',response_model=ArtifactView)
def artifact_metadata(artifact_id:str,session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).asset_dto(asset_row(session,artifact_id,True),True)

def content(session,service,key,generated):
    row=asset_row(session,key,generated)
    if row['generation_status']!='READY': raise PersistenceError('ASSET_NOT_READY','Asset is not ready for download.',409)
    if row['storage_backend']!='LOCAL': raise PersistenceError('STORAGE_UNAVAILABLE','Storage backend is not configured.',503)
    try: path=service.assets.verified_path(row['storage_key'],row['sha256'],row['byte_size'])
    except AssetUnavailable as exc: raise PersistenceError('ASSET_UNAVAILABLE',str(exc),404) from None
    media={'GLB':'model/gltf-binary','JSON':'application/json','PY':'text/x-python','STEP':'application/step'}.get(row['file_format'],'application/octet-stream')
    return FileResponse(path,media_type=media,filename=f"{key}.{row['file_format'].lower()}",headers={'ETag':row['sha256'],'Cache-Control':'private, max-age=31536000, immutable'})

@router.get('/assets/{asset_id}/content')
def asset_content(asset_id:str,session=Depends(get_session),service=Depends(get_service)):
    return content(session,service,asset_id,False)

@router.get('/artifacts/{artifact_id}/content')
def artifact_content(artifact_id:str,session=Depends(get_session),service=Depends(get_service)):
    return content(session,service,artifact_id,True)
