"""
Manifetch NICU — Inference Controller
=======================================
LLD: InferenceController sınıfı
Endpoint: POST /ai/infer

DÜZELTME 1: runInference CPU-bound — run_in_executor ile thread pool'a taşındı.
DÜZELTME 2: AI skoru yüksekse otomatik alert üretilir (sepsis ≥ 0.75, cardiac ≥ 0.75).
DÜZELTME 3: Cooldown hastalık bazlı — sepsis ve cardiac için ayrı ayrı 5 dakika.
"""

import asyncio
import threading
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Tuple

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_module.inference_service import InferenceService, VitalMeasurement
from backend.db.base import get_db
from backend.db.models import AIResult as AIResultModel, Alert
from backend.db.enums import AlertStatus, Severity
from backend.api.auth import require_any_role
from backend.db.models import User

router = APIRouter(prefix="/ai", tags=["AI Inference"])

AI_ALERT_THRESHOLD = 0.75
AI_ALERT_COOLDOWN  = 300  # saniye — hastalık bazlı 5 dakika cooldown

# In-memory cooldown: (patient_id, disease) → son alert zamanı
_ai_alert_cooldown: Dict[Tuple[str, str], datetime] = {}
_cooldown_lock = threading.Lock()

_service: Optional[InferenceService] = None
_service_lock = threading.Lock()


def get_service() -> InferenceService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
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
    resultId:        str
    patientId:       str
    timeStamp:       str
    riskScore:       float
    riskLevel:       str  = Field(..., description="LOW | MEDIUM | HIGH")
    sepsis_score:    float
    apnea_score:     float
    cardiac_score:   float
    sepsis_label:    int
    apnea_label:     int
    cardiac_label:   int
    shap_top3:       dict
    formattedResult: str


# ── Yardımcı: AI alert üret ───────────────────────────────────────────────────

def _create_ai_alerts(db: Session, patient_id: str, result) -> list:
    """
    Sepsis veya cardiac skoru eşiği geçince HIGH alert üretir.
    Cooldown hastalık bazlı — sepsis için ayrı, cardiac için ayrı 5 dakika.
    """
    scores = {
        "sepsis":  result.sepsis_score,
        "cardiac": result.cardiac_score,
        "apnea":   result.apnea_score,
    }

    now = datetime.now(timezone.utc)
    triggered = []

    with _cooldown_lock:
        for disease, score in scores.items():
            if score < AI_ALERT_THRESHOLD:
                continue

            key = (patient_id, disease)
            last_alert = _ai_alert_cooldown.get(key)

            if last_alert and (now - last_alert).total_seconds() < AI_ALERT_COOLDOWN:
                continue  # cooldown dolmadı

            # Alert oluştur
            alert = Alert(
                alert_id       = str(uuid.uuid4()),
                patient_id     = patient_id,
                rule_id        = None,
                measurement_id = None,
                status         = AlertStatus.ACTIVE.value,
                severity       = Severity.HIGH.value,
                created_at     = now,
            )
            db.add(alert)
            triggered.append(alert)
            _ai_alert_cooldown[key] = now
            print(f"[InferenceController] AI alert: {disease} score={score:.2f} → HIGH")

    return triggered


# ── Endpoint'ler ──────────────────────────────────────────────────────────────

@router.post("/infer", response_model=AIResultDTO)
async def infer(
    request:      InferenceRequestDTO,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
) -> AIResultDTO:
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

        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            service.runInference,
            request.patientId,
            measurements,
        )

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

            ai_alerts = _create_ai_alerts(db, request.patientId, result)
            db.commit()

            if ai_alerts:
                from backend.api.websocket_manager import notify_alert
                for alert in ai_alerts:
                    asyncio.create_task(notify_alert(alert))

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
    service = get_service()
    return {
        "status":       "ok",
        "modelVersion": service.runner.get_model_version(),
        "models":       list(service._models.keys()),
        "shap":         len(service._shap_explainers) > 0,
    }