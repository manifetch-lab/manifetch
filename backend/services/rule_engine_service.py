from sqlalchemy.orm import Session
from backend.db.models import ThresholdRule, VitalMeasurement


class RuleEngineService:
    """
    LLD: RuleEngineService
    Methods: getRulesForPatient, checkThresholds

    DÜZELTME: Metod adları ve dönüş tipleri LLD ile uyumlu hale getirildi.
      - evaluate()       → check_thresholds()  (LLD: checkThresholds)
      - list[Alert]      → list[ThresholdRule] (ihlal eden kurallar döner,
                                               Alert oluşturma AlertService.triggerAlert'te)
    """

    def __init__(self, db: Session):
        self.db = db

    def get_rules_for_patient(self, patient_id: str) -> list[ThresholdRule]:
        """LLD: getRulesForPatient(patientId) -> List<ThresholdRule>"""
        return (
            self.db.query(ThresholdRule)
            .filter(
                ThresholdRule.patient_id == patient_id,
                ThresholdRule.enabled    == True,
            )
            .all()
        )

    def check_thresholds(
        self,
        patient_id:  str,
        measurement: VitalMeasurement,
    ) -> list[ThresholdRule]:
        """
        LLD: checkThresholds(patientId, m) -> List<ThresholdRule>
        Ölçümün ihlal ettiği kuralları döner.
        Alert oluşturma sorumluluğu AlertService.triggerAlert'te.
        """
        rules = (
            self.db.query(ThresholdRule)
            .filter(
                ThresholdRule.patient_id  == patient_id,
                ThresholdRule.signal_type == measurement.signal_type,
                ThresholdRule.enabled     == True,
            )
            .all()
        )

        violated = []
        for rule in rules:
            if measurement.value < rule.min_value or measurement.value > rule.max_value:
                violated.append(rule)

        return violated