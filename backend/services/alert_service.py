from datetime import datetime
from sqlalchemy.orm import Session
from backend.db.models import Alert, VitalMeasurement
from backend.db.enums import AlertStatus
from backend.services.rule_engine_service import RuleEngineService


class AlertService:

    def __init__(self, db: Session):
        self.db = db
        self.rule_engine = RuleEngineService(db)

    def process_measurement(self, measurement: VitalMeasurement) -> list[Alert]:
        alerts = self.rule_engine.evaluate(measurement)

        new_alerts = []
        for alert in alerts:
            existing = (
                self.db.query(Alert)
                .filter(
                    Alert.patient_id == alert.patient_id,
                    Alert.rule_id    == alert.rule_id,
                    Alert.status     == AlertStatus.ACTIVE.value,
                )
                .first()
            )
            if not existing:
                self.db.add(alert)
                new_alerts.append(alert)

        if new_alerts:
            self.db.commit()

        return new_alerts

    def acknowledge(self, alert_id: str, user_id: str) -> Alert | None:
        alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not alert:
            return None
        if alert.status != AlertStatus.ACTIVE.value:
            return alert

        alert.status          = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = user_id
        self.db.commit()
        return alert

    def resolve(self, alert_id: str) -> Alert | None:
        alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not alert:
            return None

        alert.status      = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.utcnow()
        self.db.commit()
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