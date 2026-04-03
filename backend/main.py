from fastapi import FastAPI
from backend.db.base import engine, Base
from backend.db import models  # noqa: F401
from backend.api.ingestion import router as ingestion_router
from backend.api.auth import router as auth_router
from backend.api.dashboard import router as dashboard_router
from backend.api.patients import router as patients_router
from backend.api.websocket_manager import router as ws_router

app = FastAPI(
    title="Manifetch NICU API",
    description="Neonatal Intensive Care Unit Monitoring System",
    version="0.1.0",
)

Base.metadata.create_all(bind=engine)

app.include_router(ingestion_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(patients_router)
app.include_router(ws_router)

@app.get("/")
def root():
    return {"status": "ok", "service": "Manifetch NICU API"}


@app.get("/health")
def health():
    return {"status": "healthy"}