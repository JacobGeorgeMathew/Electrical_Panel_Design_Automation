from contextlib import asynccontextmanager
import logging
from app.jobs.runner import JobRunner
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
from app.api import routes_projects,routes_requirements,routes_design,routes_schematic,routes_layout,routes_cad,routes_validation,routes_catalog,routes_assets
from app.persistence.config import Settings,ConfigurationError
from app.persistence.database import Database
from app.persistence.repositories import PersistenceError
from app.services.design_errors import DesignError
from app.api import routes_documents, routes_operations, routes_jobs
from app.observability import RequestDiagnostics, public, emit, safe_code, configure
from app.security.local_session import LocalSession, LocalBoundary

def create_app(database=None, *, local_session=None):
    local_session = local_session or LocalSession.load()
    @asynccontextmanager
    async def lifespan(app):
        diagnostic_handler, previous_handlers = configure()
        db=database
        if db is None:
            try: db=Database(Settings.load())
            except ConfigurationError: pass
        app.state.database=db
        app.state.cad_executor=None
        if db is not None and db.ready():
            app.state.cad_executor=JobRunner(db)
            app.state.cad_executor.start()
        try:
            yield
        finally:
            if app.state.cad_executor is not None:
                app.state.cad_executor.shutdown()
            if db is not None: db.close()
            logging.getLogger().handlers = previous_handlers
            diagnostic_handler.close()

    app=FastAPI(title='Automated Electrical Panel Design Platform API',version='1.1.0',lifespan=lifespan)
    app.state.local_session = local_session
    app.include_router(routes_documents.router)
    app.include_router(routes_operations.router)
    app.include_router(routes_jobs.router)
    @app.exception_handler(DesignError)
    async def design_error_handler(request,exc):
        return JSONResponse(status_code=422,content=exc.as_dict())
    @app.exception_handler(PersistenceError)
    async def persistence_error_handler(request,exc):
        emit('public_error', code=exc.code)
        return JSONResponse(status_code=exc.status,content={'error':{'code':safe_code(exc.code),'message':public(exc.message)}})
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request,exc):
        # Pydantic's input/ctx and custom messages can contain arbitrary answers.
        return JSONResponse(status_code=422,content={'error': {'code': 'INVALID_REQUEST',
            'message': 'Request does not match the application contract.', 'details': [
                {'type': safe_code(e['type'].upper())} for e in exc.errors()[:100]]}})
    @app.exception_handler(Exception)
    async def unexpected_error_handler(request,exc):
        emit('public_error', code='INTERNAL_ERROR')
        return JSONResponse(status_code=500,content={'error':{'code':'INTERNAL_ERROR',
            'message':'The operation could not complete. Your saved data is retained.'}})
    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request,exc):
        conflict=isinstance(exc,IntegrityError)
        return JSONResponse(status_code=409 if conflict else 503,content={'error':{
            'code':'PERSISTENCE_CONFLICT' if conflict else 'DATABASE_UNAVAILABLE',
            'message':'This operation conflicts with saved data.' if conflict else 'PostgreSQL is unavailable. Check the service and application migrations.'}})
    app.add_middleware(LocalBoundary, session=local_session)
    app.add_middleware(CORSMiddleware,allow_origins=sorted(local_session.origins),
        allow_credentials=False,allow_methods=['GET','POST','PATCH','PUT','DELETE','OPTIONS'],
        allow_headers=['Content-Type', 'Idempotency-Key', 'X-Panel-Session', 'X-Panel-Bootstrap', 'X-Panel-Launch'],
        expose_headers=['X-Request-ID'])
    app.add_middleware(RequestDiagnostics)
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
