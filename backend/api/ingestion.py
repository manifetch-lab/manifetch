import json
import threading
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.base import get_db, SessionLocal
from backend.db.models import VitalMeasurement, SignalStream, AIResult as AIResultModel
from backend.db.enums import SignalType
from backend.services.alert_service import AlertService

router = APIRouter(prefix="/ingest", tags=["ingestion"])

# ── AI inference sayacı (hasta başına, her N ölçümde 1 inference) ────────────
# Sepsis modeli 3600s (60dk) pencere → 1Hz HR+SpO2 + 0.5Hz RR = ~9000 ölçüm/saat
# Her 300 ölçümde bir inference tetikle (~2 dakikada bir)
AI_INFERENCE_EVERY = 300
_patient_counters: dict[str, int] = defaultdict(int)
_counter_lock = threading.Lock()


class VitalPayload(BaseModel):
    measurement_id:        str
    patient_id:            str
    stream_id:             str | None = None
    signal_type:           SignalType
    value:                 float
    unit:                  str
    timestamp:             datetime
    timestamp_sec:         float
    is_valid:              bool = True
    gestational_age_weeks: int   | None = None
    postnatal_age_days:    int   | None = None
    pma_weeks:             float | None = None
    label_sepsis:          int = 0
    label_apnea:           int = 0
    label_cardiac:         int = 0
    label_healthy:         int = 0


@router.post("/vital")
async def ingest_vital(
    payload:          VitalPayload,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db),
):
    if payload.stream_id:
        stream = db.query(SignalStream).filter(
            SignalStream.stream_id == payload.stream_id,
            SignalStream.is_active == True,
        ).first()
        if not stream:
            raise HTTPException(status_code=404, detail="Stream bulunamadi veya aktif degil.")

    measurement = VitalMeasurement(
        measurement_id        = payload.measurement_id,
        patient_id            = payload.patient_id,
        stream_id             = payload.stream_id,
        signal_type           = payload.signal_type.value,
        value                 = payload.value,
        timestamp             = payload.timestamp,
        timestamp_sec         = payload.timestamp_sec,
        is_valid              = payload.is_valid,
        gestational_age_weeks = payload.gestational_age_weeks,
        postnatal_age_days    = payload.postnatal_age_days,
        pma_weeks             = payload.pma_weeks,
        label_sepsis          = payload.label_sepsis,
        label_apnea           = payload.label_apnea,
        label_cardiac         = payload.label_cardiac,
        label_healthy         = payload.label_healthy,
    )

    db.add(measurement)
    db.flush()

    # Threshold değerlendirme ve alert oluşturma
    alert_service = AlertService(db)
    triggered     = alert_service.process_measurement(measurement)

    db.commit()

    # WebSocket bildirimleri (background task — response'u bloklamaz)
    background_tasks.add_task(_ws_notify_vital, measurement)
    if triggered:
        for alert in triggered:
            background_tasks.add_task(_ws_notify_alert, alert)

    # AI inference tetikleme — her N ölçümde bir
    with _counter_lock:
        _patient_counters[payload.patient_id] += 1
        count = _patient_counters[payload.patient_id]
    if count % AI_INFERENCE_EVERY == 0:
        background_tasks.add_task(
            _run_ai_inference, payload.patient_id
        )

    return {
        "status":           "ok",
        "measurement_id":   measurement.measurement_id,
        "alerts_triggered": len(triggered),
        "alerts":           [a.alert_id for a in triggered],
    }


@router.get("/patients/{patient_id}/alerts")
def get_active_alerts(patient_id: str, db: Session = Depends(get_db)):
    alert_service = AlertService(db)
    alerts        = alert_service.get_active_alerts(patient_id)
    return [
        {
            "alert_id":   a.alert_id,
            "rule_id":    a.rule_id,
            "severity":   a.severity,
            "status":     a.status,
            "created_at": a.created_at,
        }
        for a in alerts
    ]


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, user_id: str, db: Session = Depends(get_db)):
    alert_service = AlertService(db)
    alert         = alert_service.acknowledge(alert_id, user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadi.")
    return {"status": "acknowledged", "alert_id": alert.alert_id}


@router.patch("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    alert_service = AlertService(db)
    alert         = alert_service.resolve(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadi.")
    return {"status": "resolved", "alert_id": alert.alert_id}


# ── AI inference (background task) ───────────────────────────────────────────

async def _run_ai_inference(patient_id: str) -> None:
    """
    DB'den son ölçümleri alıp AI inference çalıştırır.
    Sonucu ai_results tablosuna + WebSocket'e yazar.
    Async fonksiyon — BackgroundTasks event loop'da çalıştırır.
    """
    try:
        from ai_module.inference_controller import get_service
        from ai_module.inference_service import VitalMeasurement as AIVital

        db = SessionLocal()
        try:
            # En büyük pencere sepsis=3600s → 1Hz sinyallerle ~9000 ölçüm
            # Yeterli veri için son 10000 ölçümü çek
            recent = (
                db.query(VitalMeasurement)
                .filter(
                    VitalMeasurement.patient_id == patient_id,
                    VitalMeasurement.is_valid == True,
                )
                .order_by(desc(VitalMeasurement.timestamp))
                .limit(10000)
                .all()
            )

            if len(recent) < 100:
                return

            measurements = [
                AIVital(
                    patientId=m.patient_id,
                    timestamp_sec=m.timestamp_sec,
                    signalType=m.signal_type,
                    value=m.value,
                    gestationalAgeWeeks=m.gestational_age_weeks or 30,
                    postnatalAgeDays=m.postnatal_age_days or 14,
                    pma_weeks=m.pma_weeks or 32.0,
                )
                for m in recent
            ]

            service = get_service()
            result = service.runInference(patient_id, measurements)

            ai_record = AIResultModel(
                result_id=result.resultId,
                patient_id=result.patientId,
                timestamp=result.timeStamp,
                risk_score=result.riskScore,
                risk_level=result.riskLevel,
                sepsis_score=result.sepsis_score,
                apnea_score=result.apnea_score,
                cardiac_score=result.cardiac_score,
                sepsis_label=result.sepsis_label,
                apnea_label=result.apnea_label,
                cardiac_label=result.cardiac_label,
                model_used=service.runner.get_model_version(),
                shap_values_json=json.dumps(result.shap_top3),
            )
            db.add(ai_record)
            db.commit()

            # WebSocket push — AI sonucunu frontend'e bildir
            await _ws_notify_ai_result(patient_id, result.to_dict())

            print(f"[AI] {patient_id[:8]}: {result.getFormattedResult()}")

        finally:
            db.close()

    except Exception as e:
        import traceback
        print(f"[AI] Inference hatası ({patient_id[:8]}): {e}")
        traceback.print_exc()


# ── WebSocket yardımcı fonksiyonları ─────────────────────────────────────────

async def _ws_notify_ai_result(patient_id: str, result_data: dict) -> None:
    try:
        from backend.api.websocket_manager import manager
        data = {"type": "ai_result", "patient_id": patient_id, "data": result_data}
        await manager.broadcast_vital(patient_id, data)
    except Exception:
        pass


async def _ws_notify_vital(measurement) -> None:
    try:
        from backend.api.websocket_manager import notify_vital
        await notify_vital(measurement)
    except Exception:
        pass


async def _ws_notify_alert(alert) -> None:
    try:
        from backend.api.websocket_manager import notify_alert
        await notify_alert(alert)
    except Exception:
        pass