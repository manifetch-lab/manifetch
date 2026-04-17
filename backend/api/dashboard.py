from datetime import datetime, timedelta, timezone
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func

from backend.db.base import get_db
from backend.db.models import Patient, Alert, AIResult, VitalMeasurement, ThresholdRule
from backend.db.enums import AlertStatus, SignalType
from backend.api.auth import require_any_role, require_nurse, require_doctor, get_current_user
from backend.db.models import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── DTO'lar ───────────────────────────────────────────────────────────────────

class PatientDTO(BaseModel):
    patient_id:            str
    full_name:             str
    gestational_age_weeks: int
    postnatal_age_days:    int
    admission_date:        datetime
    is_active:             bool
    alert_status:          str = "STABLE"
    class Config:
        from_attributes = True


class AlertDTO(BaseModel):
    alert_id:        str
    patient_id:      str
    rule_id:         Optional[str]
    measurement_id:  Optional[str]
    status:          str
    severity:        str
    signal_type:     Optional[str] = None
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
    sepsis_score:     float
    apnea_score:      float
    cardiac_score:    float
    sepsis_label:     int
    apnea_label:      int
    cardiac_label:    int
    model_used:       str
    shap_values_json: Optional[str]
    class Config:
        from_attributes = True


class TrendPoint(BaseModel):
    timestamp_sec: float
    value:         float
    signal_type:   str
    timestamp:     str


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _compute_pna(patient) -> int:
    try:
        admission = patient.admission_date
        if admission.tzinfo is None:
            admission = admission.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - admission).days
        return patient.postnatal_age_days + days_since
    except Exception:
        return patient.postnatal_age_days


def _batch_alert_status(db: Session, patient_ids: list[str]) -> dict[str, str]:
    if not patient_ids:
        return {}
    rows = (
        db.query(Alert.patient_id, Alert.severity)
        .filter(
            Alert.patient_id.in_(patient_ids),
            Alert.status.in_([AlertStatus.ACTIVE.value, AlertStatus.ACKNOWLEDGED.value]),
        )
        .all()
    )
    result: dict[str, str] = {pid: "STABLE" for pid in patient_ids}
    for patient_id, severity in rows:
        if severity in ("HIGH", "CRITICAL"):
            result[patient_id] = "CRITICAL"
        elif result[patient_id] != "CRITICAL":
            result[patient_id] = "MONITORING"
    return result


# ── Endpoint'ler ──────────────────────────────────────────────────────────────

@router.get("/patients", response_model=list[PatientDTO])
def get_patients(
    active_only:  bool = True,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
    query = db.query(Patient)
    if active_only:
        query = query.filter(Patient.is_active == True)
    patients = query.order_by(desc(Patient.admission_date)).all()
    patient_ids  = [p.patient_id for p in patients]
    alert_status = _batch_alert_status(db, patient_ids)
    return [
        PatientDTO(
            patient_id            = p.patient_id,
            full_name             = p.full_name,
            gestational_age_weeks = p.gestational_age_weeks,
            postnatal_age_days    = _compute_pna(p),
            admission_date        = p.admission_date,
            is_active             = p.is_active,
            alert_status          = alert_status.get(p.patient_id, "STABLE"),
        )
        for p in patients
    ]


@router.get("/patients/{patient_id}", response_model=PatientDTO)
def get_patient_details(
    patient_id:   str,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
    alert_status = _batch_alert_status(db, [patient_id])
    return PatientDTO(
        patient_id            = patient.patient_id,
        full_name             = patient.full_name,
        gestational_age_weeks = patient.gestational_age_weeks,
        postnatal_age_days    = _compute_pna(patient),
        admission_date        = patient.admission_date,
        is_active             = patient.is_active,
        alert_status          = alert_status.get(patient_id, "STABLE"),
    )


@router.get("/patients/{patient_id}/alerts", response_model=list[AlertDTO])
def get_active_alerts(
    patient_id:   str,
    status:       Optional[str] = Query(None),
    limit:        int = Query(50, ge=1, le=200),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
    query = db.query(Alert).filter(Alert.patient_id == patient_id)
    if status:
        query = query.filter(Alert.status == status)
    else:
        query = query.filter(Alert.status.in_([AlertStatus.ACTIVE.value, AlertStatus.ACKNOWLEDGED.value]))
    alerts = query.options(joinedload(Alert.rule)).order_by(desc(Alert.created_at)).limit(limit).all()
    return [
        AlertDTO(
            alert_id        = a.alert_id,
            patient_id      = a.patient_id,
            rule_id         = a.rule_id,
            measurement_id  = a.measurement_id,
            status          = a.status,
            severity        = a.severity,
            signal_type     = a.rule.signal_type if a.rule else None,
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
    current_user: User    = Depends(require_nurse),
):
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadı.")
    if alert.status != AlertStatus.ACTIVE.value:
        return {"status": alert.status, "alert_id": alert_id}
    alert.status          = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = current_user.user_id
    db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


@router.patch("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id:     str,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_nurse),
):
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert bulunamadı.")
    if alert.status == AlertStatus.ACTIVE.value:
        raise HTTPException(status_code=400, detail="Alert önce onaylanmalıdır (ACKNOWLEDGED → RESOLVED).")
    if alert.status == AlertStatus.RESOLVED.value:
        return {"status": "already_resolved", "alert_id": alert_id}
    alert.status      = AlertStatus.RESOLVED.value
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "resolved", "alert_id": alert_id}


@router.get("/patients/{patient_id}/vitals", response_model=list[VitalDTO])
def get_latest_vitals(
    patient_id:   str,
    signal_type:  Optional[str] = Query(None),
    limit:        int = Query(100, ge=1, le=1000),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
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


@router.get("/patients/{patient_id}/trends", response_model=list[TrendPoint])
def get_trend_data(
    patient_id:   str,
    signal_type:  str = Query(...),
    hours:        int = Query(24, ge=1, le=168),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
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
        TrendPoint(
            timestamp_sec = m.timestamp_sec,
            value         = m.value,
            signal_type   = m.signal_type,
            timestamp     = m.timestamp.isoformat(),
        )
        for m in measurements
    ]


@router.get("/patients/{patient_id}/ai", response_model=list[AIResultDTO])
def get_ai_results(
    patient_id:   str,
    limit:        int = Query(10, ge=1, le=100),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_any_role),
):
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
            sepsis_score     = r.sepsis_score,
            apnea_score      = r.apnea_score,
            cardiac_score    = r.cardiac_score,
            sepsis_label     = r.sepsis_label,
            apnea_label      = r.apnea_label,
            cardiac_label    = r.cardiac_label,
            model_used       = r.model_used,
            shap_values_json = r.shap_values_json,
        )
        for r in results
    ]


@router.get("/patients/{patient_id}/report")
def get_pdf_report(
    patient_id:   str,
    days:         int = Query(7, ge=1, le=30),
    lang:         str = Query("tr"),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_doctor),
):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    alerts = (
        db.query(Alert)
        .options(joinedload(Alert.rule))
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

    pna         = _compute_pna(patient)
    pdf_content = _generate_pdf(patient, alerts, ai_results, days, pna, lang)

    patient_name = patient.full_name.replace(" ", "_")
    date_str     = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=NICU_Report_{patient_name}_{date_str}.pdf"
        },
    )


def _generate_pdf(patient, alerts, ai_results, days: int, pna: int, lang: str = "tr") -> bytes:
    is_tr = (lang == "tr")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return f"Manifetch NICU Clinical Report\nPatient: {patient.full_name}\n".encode("utf-8")

    import os as _os, uuid as _uuid

    FONT = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        _os.path.join(_os.path.dirname(__file__), "DejaVuSans.ttf"),
    ]
    for fp in font_paths:
        if _os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("TurkishFont", fp))
                FONT = "TurkishFont"
                FONT_BOLD = "TurkishFont"
                break
            except Exception:
                pass

    _uid = _uuid.uuid4().hex[:8]
    title_style   = ParagraphStyle(f"CT_{_uid}", fontName=FONT_BOLD, fontSize=20, spaceAfter=6,  alignment=1, textColor=colors.HexColor('#0d2d5e'))
    subtitle_style= ParagraphStyle(f"CS_{_uid}", fontName=FONT,      fontSize=10, spaceAfter=16, alignment=1, textColor=colors.grey)
    heading_style = ParagraphStyle(f"CH_{_uid}", fontName=FONT_BOLD, fontSize=13, spaceAfter=8,  spaceBefore=16, textColor=colors.HexColor('#0d2d5e'))
    normal_style  = ParagraphStyle(f"CN_{_uid}", fontName=FONT,      fontSize=10, spaceAfter=6)
    small_style   = ParagraphStyle(f"CSM_{_uid}",fontName=FONT,      fontSize=8,  textColor=colors.grey, spaceAfter=4)

    SIGNAL_LABELS = {
        "HEART_RATE": "Kalp Atışı"   if is_tr else "Heart Rate",
        "SPO2":       "SpO₂",
        "RESP_RATE":  "Solunum Hızı" if is_tr else "Resp. Rate",
        "ECG":        "ECG",
    }

    def make_table_style(header_color=colors.HexColor('#0d2d5e')):
        return TableStyle([
            ("FONTNAME",    (0, 0), (-1, -1), FONT),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("FONTNAME",    (0, 0), (-1, 0),  FONT_BOLD),
            ("BACKGROUND",  (0, 0), (-1, 0),  header_color),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
            ("ALIGN",       (0, 0), (-1, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
            ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
            ("TOPPADDING",  (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0,0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ])

    buffer = BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                               topMargin=2*cm, bottomMargin=2*cm,
                               leftMargin=2*cm, rightMargin=2*cm)
    story  = []

    # ── Başlık ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Manifetch NICU", title_style))
    story.append(Paragraph(
        ("Klinik İzlem Raporu" if is_tr else "Clinical Monitoring Report"),
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0d2d5e')))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        f"{'Oluşturulma tarihi' if is_tr else 'Generated on'}: "
        f"{datetime.now().strftime('%d.%m.%Y %H:%M')}",
        small_style,
    ))
    story.append(Spacer(1, 0.3*cm))

    # ── Hasta Bilgileri ───────────────────────────────────────────────────────
    story.append(Paragraph("Hasta Bilgileri" if is_tr else "Patient Information", heading_style))
    patient_data = [
        ["Ad Soyad" if is_tr else "Full Name",              patient.full_name],
        ["Gestasyonel Yaş" if is_tr else "Gestational Age", f"{patient.gestational_age_weeks} {'hafta' if is_tr else 'weeks'}"],
        ["Postnatal Yaş"   if is_tr else "Postnatal Age",   f"{pna} {'gün' if is_tr else 'days'}"],
        ["Kabul Tarihi"    if is_tr else "Admission Date",  patient.admission_date.strftime("%d.%m.%Y")],
        ["Rapor Dönemi"    if is_tr else "Report Period",   f"{'Son' if is_tr else 'Last'} {days} {'gün' if is_tr else 'days'}"],
    ]
    t_pat = Table(patient_data, colWidths=[5*cm, 11*cm])
    pat_style = TableStyle([
        ("FONTNAME",    (0, 0), (-1, -1), FONT),
        ("FONTNAME",    (0, 0), (0, -1),  FONT_BOLD),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("BACKGROUND",  (0, 0), (0, -1),  colors.HexColor('#eef2f7')),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0,0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ])
    t_pat.setStyle(pat_style)
    story.append(t_pat)

    # ── Alert Kayıtları ───────────────────────────────────────────────────────
    story.append(Paragraph(
        f"{'Alarm Kayıtları' if is_tr else 'Alert Records'} ({len(alerts)} {'kayıt' if is_tr else 'records'})",
        heading_style,
    ))
    if alerts:
        alert_header = [
            "Tarih" if is_tr else "Date",
            "Sinyal" if is_tr else "Signal",
            "Şiddet" if is_tr else "Severity",
            "Durum" if is_tr else "Status",
        ]
        alert_data = [alert_header]
        for a in alerts[:25]:
            signal = SIGNAL_LABELS.get(a.rule.signal_type, "AI Risk") if a.rule else "AI Risk"
            alert_data.append([
                a.created_at.strftime("%d.%m.%Y %H:%M"),
                signal,
                a.severity,
                a.status,
            ])
        t_alert = Table(alert_data, colWidths=[5*cm, 4*cm, 3*cm, 4*cm])
        t_alert.setStyle(make_table_style())
        # Severity renklendir
        for i, a in enumerate(alerts[:25], start=1):
            if a.severity == "HIGH":
                t_alert.setStyle(TableStyle([("TEXTCOLOR", (2, i), (2, i), colors.HexColor('#c62828'))]))
            elif a.severity == "MEDIUM":
                t_alert.setStyle(TableStyle([("TEXTCOLOR", (2, i), (2, i), colors.HexColor('#e65100'))]))
        story.append(t_alert)
        if len(alerts) > 25:
            story.append(Paragraph(
                f"... {'ve' if is_tr else 'and'} {len(alerts)-25} {'daha' if is_tr else 'more'}",
                small_style,
            ))
    else:
        story.append(Paragraph(
            "Bu dönemde alarm kaydı bulunmamaktadır." if is_tr else "No alerts recorded in this period.",
            normal_style,
        ))

    # ── AI Risk Değerlendirmesi ───────────────────────────────────────────────
    story.append(Paragraph(
        f"{'AI Risk Değerlendirmesi' if is_tr else 'AI Risk Assessment'} ({len(ai_results)} {'kayıt' if is_tr else 'records'})",
        heading_style,
    ))
    if ai_results:
        ai_header = [
            "Tarih" if is_tr else "Date",
            "Sepsis",
            "Apnea" if not is_tr else "Apne",
            "Kardiyak" if is_tr else "Cardiac",
            "Seviye" if is_tr else "Level",
        ]
        ai_data = [ai_header]
        for r in ai_results[:15]:
            ai_data.append([
                r.timestamp.strftime("%d.%m.%Y %H:%M"),
                f"{(r.sepsis_score or 0)*100:.1f}%",
                f"{(r.apnea_score or 0)*100:.1f}%",
                f"{(r.cardiac_score or 0)*100:.1f}%",
                r.risk_level,
            ])
        t_ai = Table(ai_data, colWidths=[5*cm, 3*cm, 3*cm, 3*cm, 2.5*cm])
        t_ai.setStyle(make_table_style(header_color=colors.HexColor('#1a5276')))
        story.append(t_ai)
    else:
        story.append(Paragraph(
            "Bu dönemde AI değerlendirmesi bulunmamaktadır." if is_tr else "No AI assessment in this period.",
            normal_style,
        ))

    # ── Sorumluluk Reddi ──────────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.2*cm))
    disclaimer = (
        "Bu rapor Manifetch NICU izleme sistemi tarafından otomatik oluşturulmuştur. "
        "Klinik karar desteği amacıyla sunulmakta olup sertifikalı tıbbi cihazların yerini tutmaz."
    ) if is_tr else (
        "This report was automatically generated by the Manifetch NICU monitoring system. "
        "It supports clinical decision-making and does not replace certified medical devices."
    )
    story.append(Paragraph(disclaimer, small_style))

    doc.build(story)
    return buffer.getvalue()