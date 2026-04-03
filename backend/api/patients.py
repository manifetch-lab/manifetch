

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.db.models import Patient, SignalStream, ThresholdRule
from backend.db.enums import SignalType, Severity
from backend.api.auth import require_nurse, require_admin, require_any_role
from backend.db.models import User

router = APIRouter(prefix="/patients", tags=["patients"])


# ── Pydantic Modelleri ────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    full_name:             str
    gestational_age_weeks: int
    postnatal_age_days:    int

    @field_validator("gestational_age_weeks")
    @classmethod
    def validate_ga(cls, v):
        if not 22 <= v <= 42:
            raise ValueError("Gestasyonel yaş 22-42 hafta arasında olmalıdır.")
        return v

    @field_validator("postnatal_age_days")
    @classmethod
    def validate_pna(cls, v):
        if not 0 <= v <= 365:
            raise ValueError("Postnatal yaş 0-365 gün arasında olmalıdır.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Ad soyad boş olamaz.")
        return v.strip()


class PatientUpdate(BaseModel):
    full_name:          Optional[str] = None
    postnatal_age_days: Optional[int] = None


class PatientResponse(BaseModel):
    patient_id:            str
    full_name:             str
    gestational_age_weeks: int
    postnatal_age_days:    int
    admission_date:        datetime
    is_active:             bool


class StreamResponse(BaseModel):
    stream_id:  str
    patient_id: str
    is_active:  bool
    started_at: datetime
    stopped_at: Optional[datetime]


# ── Varsayılan Threshold Kuralları ────────────────────────────────────────────

def _create_default_thresholds(db: Session, patient_id: str,
                                ga_weeks: int) -> list[ThresholdRule]:
    """GA'ya göre hasta özel threshold kuralları oluşturur."""

    # GA bazlı eşikler
    if ga_weeks < 28:
        hr_min, hr_max     = 100, 200
        spo2_min, spo2_max = 85, 98
        rr_min, rr_max     = 20, 80
    elif ga_weeks < 32:
        hr_min, hr_max     = 100, 190
        spo2_min, spo2_max = 87, 98
        rr_min, rr_max     = 25, 75
    elif ga_weeks < 36:
        hr_min, hr_max     = 100, 180
        spo2_min, spo2_max = 88, 98
        rr_min, rr_max     = 25, 70
    else:
        hr_min, hr_max     = 100, 170
        spo2_min, spo2_max = 90, 100
        rr_min, rr_max     = 30, 65

    rules_config = [
        (SignalType.HEART_RATE.value, hr_min,   hr_max,   Severity.HIGH.value),
        (SignalType.SPO2.value,       spo2_min, spo2_max, Severity.HIGH.value),
        (SignalType.RESP_RATE.value,  rr_min,   rr_max,   Severity.MEDIUM.value),
    ]

    rules = []
    for signal_type, min_val, max_val, severity in rules_config:
        rule = ThresholdRule(
            rule_id     = str(uuid.uuid4()),
            patient_id  = patient_id,
            signal_type = signal_type,
            min_value   = min_val,
            max_value   = max_val,
            enabled     = True,
            severity    = severity,
        )
        db.add(rule)
        rules.append(rule)

    return rules


# ── Endpoint'ler ──────────────────────────────────────────────────────────────

@router.post("", response_model=PatientResponse, status_code=201)
def create_patient(
    payload:      PatientCreate,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Yeni hasta oluştur — NURSE veya DOCTOR yetkisi gerekli."""

    # Duplikat kontrol — aynı isim ve GA
    existing = db.query(Patient).filter(
        Patient.is_active == True,
    ).all()
    for p in existing:
        if (p.full_name == payload.full_name and
                p.gestational_age_weeks == payload.gestational_age_weeks):
            raise HTTPException(
                status_code=409,
                detail="Aynı isim ve gestasyonel yaşa sahip aktif hasta zaten mevcut."
            )

    patient = Patient(
        patient_id            = str(uuid.uuid4()),
        gestational_age_weeks = payload.gestational_age_weeks,
        postnatal_age_days    = payload.postnatal_age_days,
        is_active             = True,
    )
    patient.full_name = payload.full_name  # AES-256 şifreli setter

    db.add(patient)
    db.flush()

    # Varsayılan threshold kuralları oluştur
    _create_default_thresholds(db, patient.patient_id, payload.gestational_age_weeks)

    db.commit()

    return PatientResponse(
        patient_id            = patient.patient_id,
        full_name             = patient.full_name,
        gestational_age_weeks = patient.gestational_age_weeks,
        postnatal_age_days    = patient.postnatal_age_days,
        admission_date        = patient.admission_date,
        is_active             = patient.is_active,
    )


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id:   str,
    payload:      PatientUpdate,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Hasta bilgilerini güncelle."""
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
    if not patient.is_active:
        raise HTTPException(status_code=400, detail="Arşivlenmiş hasta kaydı düzenlenemez.")

    if payload.full_name is not None:
        patient.full_name = payload.full_name
    if payload.postnatal_age_days is not None:
        patient.postnatal_age_days = payload.postnatal_age_days

    db.commit()

    return PatientResponse(
        patient_id            = patient.patient_id,
        full_name             = patient.full_name,
        gestational_age_weeks = patient.gestational_age_weeks,
        postnatal_age_days    = patient.postnatal_age_days,
        admission_date        = patient.admission_date,
        is_active             = patient.is_active,
    )


@router.patch("/{patient_id}/archive")
def archive_patient(
    patient_id:   str,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Hastayı arşivle — aktif stream'leri durdurur."""
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")

    patient.is_active = False

    # Aktif stream'leri durdur
    active_streams = db.query(SignalStream).filter(
        SignalStream.patient_id == patient_id,
        SignalStream.is_active  == True,
    ).all()
    for stream in active_streams:
        stream.is_active  = False
        stream.stopped_at = datetime.utcnow()

    db.commit()
    return {"status": "archived", "patient_id": patient_id,
            "streams_stopped": len(active_streams)}


@router.get("/{patient_id}/streams", response_model=list[StreamResponse])
def get_streams(
    patient_id:   str,
    active_only:  bool = True,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Hasta sinyal akışlarını listele."""
    query = db.query(SignalStream).filter(SignalStream.patient_id == patient_id)
    if active_only:
        query = query.filter(SignalStream.is_active == True)
    streams = query.all()
    return [
        StreamResponse(
            stream_id  = s.stream_id,
            patient_id = s.patient_id,
            is_active  = s.is_active,
            started_at = s.started_at,
            stopped_at = s.stopped_at,
        )
        for s in streams
    ]


@router.post("/{patient_id}/streams", response_model=StreamResponse, status_code=201)
def start_stream(
    patient_id:   str,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Yeni sinyal akışı başlat."""
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.is_active  == True,
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Aktif hasta bulunamadı.")

    stream = SignalStream(
        stream_id  = str(uuid.uuid4()),
        patient_id = patient_id,
        is_active  = True,
    )
    db.add(stream)
    db.commit()

    return StreamResponse(
        stream_id  = stream.stream_id,
        patient_id = stream.patient_id,
        is_active  = stream.is_active,
        started_at = stream.started_at,
        stopped_at = stream.stopped_at,
    )


@router.patch("/streams/{stream_id}/stop")
def stop_stream(
    stream_id:    str,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Sinyal akışını durdur."""
    stream = db.query(SignalStream).filter(SignalStream.stream_id == stream_id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream bulunamadı.")

    stream.is_active  = False
    stream.stopped_at = datetime.utcnow()
    db.commit()
    return {"status": "stopped", "stream_id": stream_id}