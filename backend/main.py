from fastapi import FastAPI
from backend.db.base import engine, Base
from backend.db import models  # noqa: F401
from backend.api.ingestion import router as ingestion_router

app = FastAPI(
    title="Manifetch NICU API",
    description="Neonatal Intensive Care Unit Monitoring System",
    version="0.1.0",
)

Base.metadata.create_all(bind=engine)

app.include_router(ingestion_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Manifetch NICU API"}


@app.get("/health")
def health():
    return {"status": "healthy"}