from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.db.base import get_db
from backend.db.models import VitalMeasurement, SignalStream
from backend.db.enums import SignalType
from backend.services.alert_service import AlertService

router = APIRouter(prefix="/ingest", tags=["ingestion"])


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
    gestational_age_weeks: int  | None = None
    postnatal_age_days:    int  | None = None
    pma_weeks:             float | None = None
    label_sepsis:          int = 0
    label_apnea:           int = 0
    label_cardiac:         int = 0
    label_healthy:         int = 0


@router.post("/vital")
def ingest_vital(payload: VitalPayload, db: Session = Depends(get_db)):
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
        unit                  = payload.unit,
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
    triggered = alert_service.process_measurement(measurement)

    db.commit()

    return {
        "status":          "ok",
        "measurement_id":  measurement.measurement_id,
        "alerts_triggered": len(triggered),
        "alerts":          [a.alert_id for a in triggered],
    }


@router.get("/patients/{patient_id}/alerts")
def get_active_alerts(patient_id: str, db: Session = Depends(get_db)):
    alert_service = AlertService(db)
    alerts = alert_service.get_active_alerts(patient_id)
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
    alert = alert_service.acknowledge(alert_id, user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadi.")
    return {"status": "acknowledged", "alert_id": alert.alert_id}


@router.patch("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    alert_service = AlertService(db)
    alert = alert_service.resolve(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadi.")
    return {"status": "resolved", "alert_id": alert.alert_id}