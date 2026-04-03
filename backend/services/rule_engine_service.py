from sqlalchemy.orm import Session
from backend.db.models import ThresholdRule, VitalMeasurement, Alert
from backend.db.enums import AlertStatus


class RuleEngineService:

    def __init__(self, db: Session):
        self.db = db

    def evaluate(self, measurement: VitalMeasurement) -> list[Alert]:
        rules = (
            self.db.query(ThresholdRule)
            .filter(
                ThresholdRule.patient_id  == measurement.patient_id,
                ThresholdRule.signal_type == measurement.signal_type,
                ThresholdRule.enabled     == True,
            )
            .all()
        )

        triggered = []
        for rule in rules:
            if measurement.value < rule.min_value or measurement.value > rule.max_value:
                alert = Alert(
                    patient_id     = measurement.patient_id,
                    rule_id        = rule.rule_id,
                    measurement_id = measurement.measurement_id,
                    status         = AlertStatus.ACTIVE.value,
                    severity       = rule.severity,
                )
                triggered.append(alert)

        return triggered