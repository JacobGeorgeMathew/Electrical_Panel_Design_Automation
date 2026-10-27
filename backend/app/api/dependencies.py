from fastapi import Depends, Request
from app.persistence.repositories import PersistenceError
from app.services.project_service import ProjectService

def get_database(request: Request):
    db=getattr(request.app.state,'database',None)
    if db is None:
        raise PersistenceError('DATABASE_UNAVAILABLE','Configure PostgreSQL and apply the application migrations.',503)
    return db

def get_session(database=Depends(get_database)):
    with database.sessions() as session:
        yield session

def get_service(request: Request,database=Depends(get_database)):
    return ProjectService(database,getattr(request.app.state,'cad_executor',None))
