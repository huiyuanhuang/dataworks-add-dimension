from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from routers import projects, analysis, execution, downstream

app = FastAPI(title="DataWorks Add Dimension API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(execution.router, prefix="/api/execution", tags=["execution"])
app.include_router(downstream.router, prefix="/api/downstream", tags=["downstream"])

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Serve frontend static files
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
