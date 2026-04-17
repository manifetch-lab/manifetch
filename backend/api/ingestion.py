from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.db.models import VitalMeasurement, SignalStream
from backend.db.enums import SignalType
from backend.services.alert_service import AlertService
from backend.api.auth import require_any_role, require_nurse, get_current_user
from backend.db.models import User

router = APIRouter(prefix="/ingest", tags=["ingestion"])

# Signal type → unit eşlemesi
SIGNAL_UNITS = {
    SignalType.HEART_RATE.value: "BPM",
    SignalType.SPO2.value:       "%",
    SignalType.RESP_RATE.value:  "breaths/min",
    SignalType.ECG.value:        "mV",
}


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
    current_user:     User    = Depends(require_any_role),
):
    """
    Simülasyon katmanından gelen ölçümü alır.
    Tüm roller erişebilir; kimlik doğrulaması zorunlu.
    """
    if payload.stream_id:
        stream = db.query(SignalStream).filter(
            SignalStream.stream_id == payload.stream_id,
            SignalStream.is_active == True,
        ).first()
        if not stream:
            raise HTTPException(status_code=404, detail="Stream bulunamadı veya aktif değil.")

    unit = SIGNAL_UNITS.get(payload.signal_type.value, payload.unit)

    measurement = VitalMeasurement(
        measurement_id        = payload.measurement_id,
        patient_id            = payload.patient_id,
        stream_id             = payload.stream_id,
        signal_type           = payload.signal_type.value,
        value                 = payload.value,
        unit                  = unit,
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

    alert_service = AlertService(db)
    triggered     = alert_service.process_measurement(measurement)

    db.commit()

    background_tasks.add_task(_ws_notify_vital, measurement)
    if triggered:
        for alert in triggered:
            background_tasks.add_task(_ws_notify_alert, alert)

    return {
        "status":           "ok",
        "measurement_id":   measurement.measurement_id,
        "alerts_triggered": len(triggered),
        "alerts":           [a.alert_id for a in triggered],
    }


@router.get("/patients/{patient_id}/alerts")
def get_active_alerts(
    patient_id:   str,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
    """Hasta için aktif alert listesi."""
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


# ── WebSocket yardımcı fonksiyonları ─────────────────────────────────────────

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
    except Exception as e:
        print(f"[WS Alert Error] {e}")


class ECGPayload(BaseModel):
    patient_id: str
    samples:    list[float]
    timestamp:  str
    fs:         int = 25


@router.post("/ecg")
async def ingest_ecg(
    payload:          ECGPayload,
    background_tasks: BackgroundTasks,
    current_user:     User = Depends(require_any_role),
):
    """ECG sample batch'ini alır ve WebSocket üzerinden frontend'e iletir."""
    background_tasks.add_task(_ws_notify_ecg, payload.patient_id, payload.samples)
    return {"status": "ok", "samples": len(payload.samples)}


async def _ws_notify_ecg(patient_id: str, samples: list) -> None:
    try:
        from backend.api.websocket_manager import notify_ecg
        await notify_ecg(patient_id, samples)
    except Exception:
        pass