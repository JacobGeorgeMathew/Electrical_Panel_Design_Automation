from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
from sqlalchemy import update
from datetime import datetime, timezone
from app.api import routes_projects,routes_requirements,routes_design,routes_schematic,routes_layout,routes_cad,routes_validation,routes_catalog,routes_assets
from app.persistence.config import Settings,ConfigurationError
from app.persistence.database import Database
from app.persistence.repositories import PersistenceError
from app.services.design_errors import DesignError

def create_app(database=None):
    @asynccontextmanager
    async def lifespan(app):
        db=database
        if db is None:
            try: db=Database(Settings.load())
            except ConfigurationError: pass
        app.state.database=db
        app.state.cad_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='panel-cad')
        if db is not None and db.ready():
            # The desktop backend uses one process; interrupted local jobs are explicit failures.
            from app.persistence import models as m
            with db.sessions.begin() as session:
                session.execute(update(m.generated_artifacts).where(m.generated_artifacts.c.generation_status=='PENDING').values(
                    generation_status='FAILED',completed_at=datetime.now(timezone.utc),error={'code':'INTERRUPTED','message':'The backend restarted before this export completed. Regenerate the saved revision.'}))
        yield
        app.state.cad_executor.shutdown(wait=True,cancel_futures=True)
        if db is not None: db.close()

    app=FastAPI(title='Automated Electrical Panel Design Platform API',version='1.1.0',lifespan=lifespan)
    @app.exception_handler(DesignError)
    async def design_error_handler(request,exc):
        return JSONResponse(status_code=422,content=exc.as_dict())
    @app.exception_handler(PersistenceError)
    async def persistence_error_handler(request,exc):
        return JSONResponse(status_code=exc.status,content={'error':{'code':exc.code,'message':exc.message}})
    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request,exc):
        conflict=isinstance(exc,IntegrityError)
        return JSONResponse(status_code=409 if conflict else 503,content={'error':{
            'code':'PERSISTENCE_CONFLICT' if conflict else 'DATABASE_UNAVAILABLE',
            'message':'This operation conflicts with saved data.' if conflict else 'PostgreSQL is unavailable. Check the service and application migrations.'}})
    app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000','tauri://localhost','http://tauri.localhost','https://tauri.localhost'],
        allow_credentials=True,allow_methods=['GET','POST','PATCH','PUT','OPTIONS'],allow_headers=['Content-Type'])
    for module in (routes_projects,routes_requirements,routes_design,routes_schematic,routes_layout,routes_cad,routes_validation,routes_catalog,routes_assets):
        app.include_router(module.router)
    @app.get('/health')
    def health():
        return {'status':'HEALTHY','service':'Electrical Panel Design Engine','archetypes':['DB'],'models':['CEM','PDM']}
    @app.get('/ready')
    def ready():
        db=getattr(app.state,'database',None)
        ok=db is not None and db.ready()
        return JSONResponse(status_code=200 if ok else 503,content={'status':'READY' if ok else 'NOT_READY',
            'database':'available' if ok else 'unavailable_or_migrations_required'})
    return app

app=create_app()
