from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes_projects import router as projects_router
from app.api.routes_requirements import router as requirements_router
from app.api.routes_design import router as design_router
from app.api.routes_schematic import router as schematic_router
from app.api.routes_layout import router as layout_router
from app.api.routes_cad import router as cad_router
from app.api.routes_validation import router as validation_router

app = FastAPI(
    title="Automated Electrical Panel Design Platform API",
    description="Backend API powered by Canonical Engineering Model (CEM) and Physical Design Model (PDM)",
    version="1.0.0"
)

# Enable CORS for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",     # vite dev (use 3000 if you're on CRA)
        "tauri://localhost",         # macOS / Linux
        "http://tauri.localhost",    # Windows
        "https://tauri.localhost",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(requirements_router)
app.include_router(design_router)
app.include_router(schematic_router)
app.include_router(layout_router)
app.include_router(cad_router)
app.include_router(validation_router)


@app.get("/health")
def health_check():
    return {
        "status": "HEALTHY",
        "service": "Electrical Panel Design Engine",
        "archetypes": ["DB", "MCC", "PLC", "VFD"],
        "models": ["CEM", "PDM"]
    }
