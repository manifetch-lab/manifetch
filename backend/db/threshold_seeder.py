import os
import sys
from backend.db.base import SessionLocal
from backend.db.models import Patient, ThresholdRule
from backend.db.enums import SignalType, Severity

# Generator'daki GA_BASELINE ile birebir uyumlu eşik değerleri
GA_THRESHOLDS = {
    (24, 29): {
        SignalType.HEART_RATE: {"min": 120, "max": 177, "severity": Severity.HIGH},
        SignalType.SPO2:       {"min": 88,  "max": 98,  "severity": Severity.CRITICAL},
        SignalType.RESP_RATE:  {"min": 30,  "max": 75,  "severity": Severity.HIGH},
    },
    (29, 33): {
        SignalType.HEART_RATE: {"min": 122, "max": 175, "severity": Severity.HIGH},
        SignalType.SPO2:       {"min": 89,  "max": 98,  "severity": Severity.CRITICAL},
        SignalType.RESP_RATE:  {"min": 30,  "max": 70,  "severity": Severity.HIGH},
    },
    (33, 37): {
        SignalType.HEART_RATE: {"min": 115, "max": 172, "severity": Severity.MEDIUM},
        SignalType.SPO2:       {"min": 90,  "max": 99,  "severity": Severity.HIGH},
        SignalType.RESP_RATE:  {"min": 30,  "max": 68,  "severity": Severity.MEDIUM},
    },
    (37, 43): {
        SignalType.HEART_RATE: {"min": 100, "max": 160, "severity": Severity.MEDIUM},
        SignalType.SPO2:       {"min": 92,  "max": 100, "severity": Severity.HIGH},
        SignalType.RESP_RATE:  {"min": 30,  "max": 65,  "severity": Severity.MEDIUM},
    },
}


def get_thresholds_for_ga(ga_weeks: int) -> dict:
    for (lo, hi), thresholds in GA_THRESHOLDS.items():
        if lo <= ga_weeks < hi:
            return thresholds
    return GA_THRESHOLDS[(37, 43)]


def seed_thresholds():
    db = SessionLocal()
    try:
        existing = db.query(ThresholdRule).count()
        if existing > 0:
            print(f"ThresholdRule tablosu zaten dolu ({existing} kural), atlanıyor.")
            return

        patients = db.query(Patient).all()
        print(f"{len(patients)} hasta için threshold kuralları oluşturuluyor...")

        rules = []
        for patient in patients:
            thresholds = get_thresholds_for_ga(patient.gestational_age_weeks)
            for signal_type, values in thresholds.items():
                rules.append(ThresholdRule(
                    patient_id  = patient.patient_id,
                    signal_type = signal_type.value,
                    min_value   = values["min"],
                    max_value   = values["max"],
                    severity    = values["severity"].value,
                    enabled     = True,
                ))

        db.bulk_save_objects(rules)
        db.commit()
        print(f"Toplam {len(rules)} kural oluşturuldu ({len(rules) // len(patients)} kural/hasta).")

    except Exception as e:
        db.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_thresholds()