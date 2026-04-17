from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.db.models import Alert, VitalMeasurement, ThresholdRule
from backend.db.enums import AlertStatus
from backend.services.rule_engine_service import RuleEngineService


class AlertService:

    def __init__(self, db: Session):
        self.db          = db
        self.rule_engine = RuleEngineService(db)

    def process_measurement(self, measurement: VitalMeasurement) -> list[Alert]:
        
        violated_rules = self.rule_engine.check_thresholds(
            measurement.patient_id, measurement
        )

        new_alerts = []
        for rule in violated_rules:
            alert = self.triggerAlert(measurement.patient_id, rule, measurement)
            if alert:
                new_alerts.append(alert)

        return new_alerts

    def triggerAlert(
        self,
        patient_id: str,
        rule:       ThresholdRule,
        measurement: VitalMeasurement,
    ) -> Alert | None:
        
        existing = (
            self.db.query(Alert)
            .filter(
                Alert.patient_id == patient_id,
                Alert.rule_id    == rule.rule_id,
                Alert.status     == AlertStatus.ACTIVE.value,
            )
            .first()
        )
        if existing:
            return None  # Zaten aktif alert var — yeni oluşturma

        alert = Alert(
            patient_id     = patient_id,
            rule_id        = rule.rule_id,
            measurement_id = measurement.measurement_id,
            status         = AlertStatus.ACTIVE.value,
            severity       = rule.severity,
        )
        self.db.add(alert)
        return alert

    def acknowledge(self, alert_id: str, user_id: str) -> Alert | None:
        
        alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not alert:
            return None
        if alert.status != AlertStatus.ACTIVE.value:
            return alert  # Zaten acknowledge/resolve edilmiş

        alert.status          = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = user_id
        # DÜZELTME: commit yok — controller commit eder
        return alert

    def resolve(self, alert_id: str) -> Alert | None:
       
        alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not alert:
            return None

        if alert.status == AlertStatus.ACTIVE.value:
            raise ValueError(
                "Alert önce onaylanmalıdır (ACKNOWLEDGED). "
                "ACTIVE → ACKNOWLEDGED → RESOLVED lifecycle'ı izleyin."
            )

        if alert.status == AlertStatus.RESOLVED.value:
            return alert  

        alert.status      = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now(timezone.utc)
        return alert

    def get_active_alerts(self, patient_id: str) -> list[Alert]:
        return (
            self.db.query(Alert)
            .filter(
                Alert.patient_id == patient_id,
                Alert.status     == AlertStatus.ACTIVE.value,
            )
            .order_by(Alert.created_at.desc())
            .all()
        )