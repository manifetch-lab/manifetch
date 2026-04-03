"""
Manifetch NICU — Inference Controller
=======================================
LLD: InferenceController sınıfı
Görev: Dışarıdan gelen inference isteklerini karşılar,
       InferenceService'e yönlendirir, AIResultDTO döndürür.

Endpoint: POST /ai/infer
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from inference_service import InferenceService, VitalMeasurement

router = APIRouter(prefix="/ai", tags=["AI Inference"])

# Singleton — uygulama başladığında bir kez yüklenir
_service: Optional[InferenceService] = None


def get_service() -> InferenceService:
    global _service
    if _service is None:
        _service = InferenceService()
    return _service


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST / RESPONSE MODELLERI
# ─────────────────────────────────────────────────────────────────────────────

class VitalMeasurementDTO(BaseModel):
    """Gelen ölçüm verisi."""
    timestamp_sec:        float
    signalType:           str   = Field(..., description="HEART_RATE | SPO2 | RESP_RATE | ECG")
    value:                float
    gestationalAgeWeeks:  int   = Field(default=30)
    postnatalAgeDays:     int   = Field(default=14)
    pma_weeks:            float = Field(default=32.0)


class InferenceRequestDTO(BaseModel):
    """POST /ai/infer request body."""
    patientId:    str
    measurements: List[VitalMeasurementDTO] = Field(
        ..., min_length=10,
        description="En az 10 ölçüm gerekli (30 saniyelik pencere önerilir)"
    )


class SHAPFeatureDTO(BaseModel):
    feature:    str
    importance: float


class AIResultDTO(BaseModel):
    """POST /ai/infer response body — LLD: AIResult."""
    resultId:      str
    patientId:     str
    timeStamp:     str
    riskScore:     float
    riskLevel:     str   = Field(..., description="LOW | MEDIUM | HIGH")
    sepsis_score:  float
    apnea_score:   float
    cardiac_score: float
    sepsis_label:  int
    apnea_label:   int
    cardiac_label: int
    shap_top3:     dict
    formattedResult: str


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/infer", response_model=AIResultDTO)
async def infer(request: InferenceRequestDTO) -> AIResultDTO:
    """
    LLD: InferenceController.infer(patientId, input) -> AIResultDTO

    Bir hasta için anlık risk değerlendirmesi yapar.

    - **patientId**: Hasta UUID
    - **measurements**: Son 30 saniyelik ölçümler (HR + SpO2 + RR + ECG)

    Döndürür:
    - riskLevel: LOW / MEDIUM / HIGH
    - sepsis_score, apnea_score, cardiac_score: 0.0-1.0
    - shap_top3: Her hastalık için en etkili 3 özellik
    """
    try:
        # DTO → VitalMeasurement dönüşümü
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

        # Inference çalıştır
        service = get_service()
        result  = service.runInference(request.patientId, measurements)

        # AIResult → AIResultDTO
        return AIResultDTO(
            resultId       = result.resultId,
            patientId      = result.patientId,
            timeStamp      = result.timeStamp.isoformat(),
            riskScore      = result.riskScore,
            riskLevel      = result.riskLevel,
            sepsis_score   = result.sepsis_score,
            apnea_score    = result.apnea_score,
            cardiac_score  = result.cardiac_score,
            sepsis_label   = result.sepsis_label,
            apnea_label    = result.apnea_label,
            cardiac_label  = result.cardiac_label,
            shap_top3      = result.shap_top3,
            formattedResult= result.getFormattedResult(),
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Inference hatası: {str(e)}")


@router.get("/health")
async def health_check():
    """AI modülü sağlık kontrolü."""
    service = get_service()
    return {
        "status":       "ok",
        "modelVersion": service.runner.get_model_version(),
        "models":       list(service.runner._models.keys()),
        "shap":         len(service._shap_explainers) > 0,
    }