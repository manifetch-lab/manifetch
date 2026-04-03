from datetime import datetime, timedelta
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.base import get_db
from backend.db.models import Patient, Alert, AIResult, VitalMeasurement, ThresholdRule
from backend.db.enums import AlertStatus, SignalType
from backend.api.auth import require_any_role, require_nurse, require_doctor, get_current_user
from backend.db.models import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Pydantic Modelleri ────────────────────────────────────────────────────────

class PatientDTO(BaseModel):
    patient_id:            str
    full_name:             str
    gestational_age_weeks: int
    postnatal_age_days:    int
    admission_date:        datetime
    is_active:             bool

    class Config:
        from_attributes = True


class AlertDTO(BaseModel):
    alert_id:        str
    patient_id:      str
    rule_id:         Optional[str]
    measurement_id:  Optional[str]
    status:          str
    severity:        str
    created_at:      datetime
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]
    resolved_at:     Optional[datetime]

    class Config:
        from_attributes = True


class VitalDTO(BaseModel):
    measurement_id: str
    signal_type:    str
    value:          float
    unit:           str
    timestamp:      datetime
    timestamp_sec:  float
    is_valid:       bool


class AIResultDTO(BaseModel):
    result_id:        str
    patient_id:       str
    timestamp:        datetime
    risk_score:       float
    risk_level:       str
    model_used:       str
    shap_values_json: Optional[str]

    class Config:
        from_attributes = True


class TrendPoint(BaseModel):
    timestamp_sec: float
    value:         float
    signal_type:   str


# ── Endpoint'ler ──────────────────────────────────────────────────────────────

@router.get("/patients", response_model=list[PatientDTO])
def get_patients(
    active_only: bool = True,
    db:          Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Tüm hastaları listele."""
    query = db.query(Patient)
    if active_only:
        query = query.filter(Patient.is_active == True)
    patients = query.order_by(desc(Patient.admission_date)).all()
    return [
        PatientDTO(
            patient_id            = p.patient_id,
            full_name             = p.full_name,
            gestational_age_weeks = p.gestational_age_weeks,
            postnatal_age_days    = p.postnatal_age_days,
            admission_date        = p.admission_date,
            is_active             = p.is_active,
        )
        for p in patients
    ]


@router.get("/patients/{patient_id}", response_model=PatientDTO)
def get_patient_details(
    patient_id:   str,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Hasta detaylarını getir."""
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
    return PatientDTO(
        patient_id            = patient.patient_id,
        full_name             = patient.full_name,
        gestational_age_weeks = patient.gestational_age_weeks,
        postnatal_age_days    = patient.postnatal_age_days,
        admission_date        = patient.admission_date,
        is_active             = patient.is_active,
    )


@router.get("/patients/{patient_id}/alerts", response_model=list[AlertDTO])
def get_active_alerts(
    patient_id:   str,
    status:       Optional[str] = Query(None, description="ACTIVE, ACKNOWLEDGED, RESOLVED"),
    limit:        int = Query(50, ge=1, le=200),
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Hasta alertlerini getir."""
    query = db.query(Alert).filter(Alert.patient_id == patient_id)
    if status:
        query = query.filter(Alert.status == status)
    else:
        query = query.filter(Alert.status == AlertStatus.ACTIVE.value)
    alerts = query.order_by(desc(Alert.created_at)).limit(limit).all()
    return [
        AlertDTO(
            alert_id        = a.alert_id,
            patient_id      = a.patient_id,
            rule_id         = a.rule_id,
            measurement_id  = a.measurement_id,
            status          = a.status,
            severity        = a.severity,
            created_at      = a.created_at,
            acknowledged_at = a.acknowledged_at,
            acknowledged_by = a.acknowledged_by,
            resolved_at     = a.resolved_at,
        )
        for a in alerts
    ]


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id:     str,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Alert'i onayla — NURSE veya DOCTOR yetkisi gerekli."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadı.")
    if alert.status != AlertStatus.ACTIVE.value:
        return {"status": alert.status, "alert_id": alert_id}

    alert.status          = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = current_user.user_id
    db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


@router.patch("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id:     str,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_nurse),
):
    """Alert'i çöz."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadı.")
    alert.status      = AlertStatus.RESOLVED.value
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"status": "resolved", "alert_id": alert_id}


@router.get("/patients/{patient_id}/vitals", response_model=list[VitalDTO])
def get_latest_vitals(
    patient_id:  str,
    signal_type: Optional[str] = Query(None),
    limit:       int = Query(100, ge=1, le=1000),
    db:          Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Son vital ölçümleri getir."""
    query = db.query(VitalMeasurement).filter(
        VitalMeasurement.patient_id == patient_id,
        VitalMeasurement.is_valid   == True,
    )
    if signal_type:
        query = query.filter(VitalMeasurement.signal_type == signal_type)

    measurements = query.order_by(desc(VitalMeasurement.timestamp)).limit(limit).all()
    return [
        VitalDTO(
            measurement_id = m.measurement_id,
            signal_type    = m.signal_type,
            value          = m.value,
            unit           = m.unit,
            timestamp      = m.timestamp,
            timestamp_sec  = m.timestamp_sec,
            is_valid       = m.is_valid,
        )
        for m in measurements
    ]


@router.get("/patients/{patient_id}/trends")
def get_trend_data(
    patient_id:  str,
    signal_type: str = Query(..., description="HEART_RATE, SPO2, RESP_RATE"),
    hours:       int = Query(24, ge=1, le=168),
    db:          Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Trend verisi — son X saatlik."""
    since = datetime.utcnow() - timedelta(hours=hours)
    measurements = (
        db.query(VitalMeasurement)
        .filter(
            VitalMeasurement.patient_id  == patient_id,
            VitalMeasurement.signal_type == signal_type,
            VitalMeasurement.timestamp   >= since,
            VitalMeasurement.is_valid    == True,
        )
        .order_by(VitalMeasurement.timestamp)
        .all()
    )
    return [
        {
            "timestamp_sec": m.timestamp_sec,
            "value":         m.value,
            "signal_type":   m.signal_type,
            "timestamp":     m.timestamp.isoformat(),
        }
        for m in measurements
    ]


@router.get("/patients/{patient_id}/ai", response_model=list[AIResultDTO])
def get_ai_results(
    patient_id:   str,
    limit:        int = Query(10, ge=1, le=100),
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Son AI sonuçlarını getir."""
    results = (
        db.query(AIResult)
        .filter(AIResult.patient_id == patient_id)
        .order_by(desc(AIResult.timestamp))
        .limit(limit)
        .all()
    )
    return [
        AIResultDTO(
            result_id        = r.result_id,
            patient_id       = r.patient_id,
            timestamp        = r.timestamp,
            risk_score       = r.risk_score,
            risk_level       = r.risk_level,
            model_used       = r.model_used,
            shap_values_json = r.shap_values_json,
        )
        for r in results
    ]


@router.get("/patients/{patient_id}/report")
def get_pdf_report(
    patient_id:   str,
    days:         int = Query(7, ge=1, le=30),
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_doctor),
):
    """PDF klinik rapor — sadece DOCTOR."""
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")

    since = datetime.utcnow() - timedelta(days=days)

    alerts = (
        db.query(Alert)
        .filter(Alert.patient_id == patient_id, Alert.created_at >= since)
        .order_by(desc(Alert.created_at))
        .all()
    )

    ai_results = (
        db.query(AIResult)
        .filter(AIResult.patient_id == patient_id, AIResult.timestamp >= since)
        .order_by(desc(AIResult.timestamp))
        .limit(20)
        .all()
    )

    # PDF içeriği oluştur
    pdf_content = _generate_pdf(patient, alerts, ai_results, days)

    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=report_{patient_id[:8]}_{datetime.now().strftime('%Y%m%d')}.pdf"
        },
    )


def _generate_pdf(patient, alerts, ai_results, days: int) -> bytes:
    """Basit PDF raporu üretir."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import ParagraphStyle
    except ImportError:
        # reportlab yoksa basit text döndür
        content = f"Manifetch NICU Clinical Report\n"
        content += f"Patient: {patient.full_name}\n"
        content += f"GA: {patient.gestational_age_weeks}w PNA: {patient.postnatal_age_days}d\n"
        content += f"Period: Last {days} days\n\n"
        content += f"Alerts: {len(alerts)}\n"
        for a in alerts:
            content += f"  [{a.severity}] {a.status} - {a.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        content += f"\nAI Results: {len(ai_results)}\n"
        for r in ai_results:
            content += f"  [{r.risk_level}] Score={r.risk_score:.3f} - {r.timestamp.strftime('%Y-%m-%d %H:%M')}\n"
        return content.encode("utf-8")

    buffer = BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                               topMargin=2*cm, bottomMargin=2*cm,
                               leftMargin=2*cm, rightMargin=2*cm)
    styles  = getSampleStyleSheet()
    story   = []

    # Başlık
    story.append(Paragraph("Manifetch NICU — Klinik Rapor", styles["Title"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"Oluşturulma tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))

    # Hasta bilgileri
    story.append(Paragraph("Hasta Bilgileri", styles["Heading2"]))
    patient_data = [
        ["Ad Soyad",          patient.full_name],
        ["Gestasyonel Yaş",   f"{patient.gestational_age_weeks} hafta"],
        ["Postnatal Yaş",     f"{patient.postnatal_age_days} gün"],
        ["Kabul Tarihi",      patient.admission_date.strftime("%d.%m.%Y")],
        ["Rapor Dönemi",      f"Son {days} gün"],
    ]
    t = Table(patient_data, colWidths=[5*cm, 10*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("PADDING",    (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # Alertler
    story.append(Paragraph(f"Alarm Kayıtları ({len(alerts)} adet)", styles["Heading2"]))
    if alerts:
        alert_data = [["Tarih", "Şiddet", "Durum"]]
        for a in alerts[:20]:
            alert_data.append([
                a.created_at.strftime("%d.%m.%Y %H:%M"),
                a.severity,
                a.status,
            ])
        t = Table(alert_data, colWidths=[6*cm, 4*cm, 5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("PADDING",    (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightyellow]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Bu dönemde alarm kaydı bulunmamaktadır.", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))

    # AI Sonuçları
    story.append(Paragraph(f"AI Risk Değerlendirmesi ({len(ai_results)} kayıt)", styles["Heading2"]))
    if ai_results:
        ai_data = [["Tarih", "Risk Skoru", "Risk Seviyesi", "Model"]]
        for r in ai_results[:15]:
            ai_data.append([
                r.timestamp.strftime("%d.%m.%Y %H:%M"),
                f"{r.risk_score:.3f}",
                r.risk_level,
                r.model_used,
            ])
        t = Table(ai_data, colWidths=[6*cm, 3*cm, 4*cm, 4*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("PADDING",    (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightblue]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Bu dönemde AI değerlendirmesi bulunmamaktadır.", styles["Normal"]))

    # Yasal not
    story.append(Spacer(1, 1*cm))
    disclaimer_style = ParagraphStyle("disclaimer", parent=styles["Normal"],
                                      fontSize=8, textColor=colors.grey)
    story.append(Paragraph(
        "Bu rapor Manifetch NICU izleme sistemi tarafından otomatik oluşturulmuştur. "
        "Klinik karar desteği amacıyla sunulmakta olup sertifikalı tıbbi cihazların yerini tutmaz. "
        "Nihai klinik kararlar uzman hekim tarafından verilmelidir.",
        disclaimer_style
    ))

    doc.build(story)
    return buffer.getvalue()