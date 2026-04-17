from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.base import engine, Base, get_db
from backend.db import models  # noqa: F401
from backend.api.ingestion        import router as ingestion_router
from backend.api.auth             import router as auth_router
from backend.api.dashboard        import router as dashboard_router
from backend.api.patients         import router as patients_router
from backend.api.websocket_manager import router as ws_router
from backend.api.admin            import router as admin_router
from backend.api.simulation     import router as simulation_router


# DÜZELTME: AI modülü router'ı eklendi — daha önce eksikti, /ai/infer çalışmıyordu
from ai_module.inference_controller import router as ai_router, get_service

import os

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    
    # Tabloları oluştur (Alembic migration'a geçilene kadar)
    Base.metadata.create_all(bind=engine)
    print("[Startup] Tablolar hazır.")

    # DÜZELTME: AI modeli startup'ta yükleniyor — ilk request'te race condition yok
    try:
        get_service()
        print("[Startup] AI modelleri yüklendi.")
    except Exception as e:
        print(f"[Startup] UYARI: AI modelleri yüklenemedi: {e}")

    yield
    # Shutdown: gerekirse cleanup buraya


app = FastAPI(
    title="Manifetch NICU API",
    description="Neonatal Intensive Care Unit Monitoring System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router'ları kaydet
app.include_router(auth_router)
app.include_router(ai_router)          # DÜZELTME: AI router eklendi
app.include_router(ingestion_router)
app.include_router(dashboard_router)
app.include_router(patients_router)
app.include_router(ws_router)
app.include_router(admin_router)
app.include_router(simulation_router)

@app.get("/")
def root():
    return {"status": "ok", "service": "Manifetch NICU API"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "db":     db_status,
    }