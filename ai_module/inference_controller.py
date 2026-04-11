"""
Manifetch NICU — Inference Controller
=======================================
LLD: InferenceController sınıfı
Endpoint: POST /ai/infer
"""

import threading
import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_module.inference_service import InferenceService, VitalMeasurement
from backend.db.base import get_db
from backend.db.models import AIResult as AIResultModel
from backend.api.auth import require_any_role
from backend.db.models import User

router = APIRouter(prefix="/ai", tags=["AI Inference"])

# DÜZELTME: Singleton thread-safe — lock ile race condition önlendi
_service: Optional[InferenceService] = None
_service_lock = threading.Lock()


def get_service() -> InferenceService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:   # double-checked locking
                _service = InferenceService()
    return _service


# ── Request / Response modelleri ─────────────────────────────────────────────

class VitalMeasurementDTO(BaseModel):
    timestamp_sec:        float
    signalType:           str   = Field(..., description="HEART_RATE | SPO2 | RESP_RATE | ECG")
    value:                float
    gestationalAgeWeeks:  int   = Field(default=30)
    postnatalAgeDays:     int   = Field(default=14)
    pma_weeks:            float = Field(default=32.0)


class InferenceRequestDTO(BaseModel):
    patientId:    str
    measurements: List[VitalMeasurementDTO] = Field(
        ..., min_length=10,
        description="En az 10 ölçüm gerekli (30 saniyelik pencere önerilir)",
    )
    save_to_db: bool = Field(default=True, description="Sonucu DB'ye kaydet")


class AIResultDTO(BaseModel):
    """LLD: AIResult — multi-label skorlar dahil."""
    resultId:       str
    patientId:      str
    timeStamp:      str
    riskScore:      float
    riskLevel:      str   = Field(..., description="LOW | MEDIUM | HIGH")
    sepsis_score:   float
    apnea_score:    float
    cardiac_score:  float
    sepsis_label:   int
    apnea_label:    int
    cardiac_label:  int
    shap_top3:      dict
    formattedResult: str


# ── Endpoint'ler ──────────────────────────────────────────────────────────────

@router.post("/infer", response_model=AIResultDTO)
async def infer(
    request:      InferenceRequestDTO,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
) -> AIResultDTO:
    """
    LLD: InferenceController.infer(patientId, input) -> AIResultDTO

    Bir hasta için anlık risk değerlendirmesi yapar.
    Sonucu isteğe bağlı olarak DB'ye kaydeder (save_to_db=True varsayılan).
    """
    try:
        measurements = [
            VitalMeasurement(
                patientId           = request.patientId,
                timestamp_sec       = m.timestamp_sec,
                signalType          = m.signalType,
                value               = m.value,
                gestationalAgeWeeks = m.gestationalAgeWeeks,
                postnatalAgeDays    = m.postnatalAgeDays,
                pma_weeks           = m.pma_weeks,
            )
            for m in request.measurements
        ]

        service = get_service()
        result  = service.runInference(request.patientId, measurements)

        # Sonucu DB'ye kaydet
        if request.save_to_db:
            ai_record = AIResultModel(
                result_id        = result.resultId,
                patient_id       = result.patientId,
                timestamp        = result.timeStamp,
                risk_score       = result.riskScore,
                risk_level       = result.riskLevel,
                sepsis_score     = result.sepsis_score,
                apnea_score      = result.apnea_score,
                cardiac_score    = result.cardiac_score,
                sepsis_label     = result.sepsis_label,
                apnea_label      = result.apnea_label,
                cardiac_label    = result.cardiac_label,
                model_used       = str(service.runner.get_model_version())[:32],
                shap_values_json = json.dumps(result.shap_top3),
            )
            db.add(ai_record)
            db.commit()

        return AIResultDTO(
            resultId        = result.resultId,
            patientId       = result.patientId,
            timeStamp       = result.timeStamp.isoformat(),
            riskScore       = result.riskScore,
            riskLevel       = result.riskLevel,
            sepsis_score    = result.sepsis_score,
            apnea_score     = result.apnea_score,
            cardiac_score   = result.cardiac_score,
            sepsis_label    = result.sepsis_label,
            apnea_label     = result.apnea_label,
            cardiac_label   = result.cardiac_label,
            shap_top3       = result.shap_top3,
            formattedResult = result.getFormattedResult(),
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference hatası: {str(e)}")


@router.get("/health")
async def health_check():
    """AI modülü sağlık kontrolü — ModelRunner artık mevcut, crash yok."""
    service = get_service()
    return {
        "status":       "ok",
        "modelVersion": service.runner.get_model_version(),
        "models":       list(service._models.keys()),
        "shap":         len(service._shap_explainers) > 0,
    }