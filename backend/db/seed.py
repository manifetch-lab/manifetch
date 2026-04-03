import json
import csv
import os
import sys
import uuid
from datetime import datetime
from backend.db.base import SessionLocal, engine
from backend.db.models import Base, Patient, VitalMeasurement

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "all_data")
METADATA_PATH = os.path.join(DATA_DIR, "patients_metadata.json")
VITALS_PATH   = os.path.join(DATA_DIR, "all_vitals.csv")

BATCH_SIZE = 5000


def parse_dt(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return datetime.utcnow()


def seed_patients(session, patients_meta: list) -> dict:
    id_map = {}
    existing = {p.patient_id for p in session.query(Patient.patient_id).all()}

    for p in patients_meta:
        pid = p["patientId"]
        if pid in existing:
            id_map[pid] = pid
            continue
        patient = Patient(
            patient_id            = pid,
            full_name             = f"Simulated Patient {pid[:8]}",
            gestational_age_weeks = p["gestationalAgeWeeks"],
            postnatal_age_days    = p["postnatalAgeDays"],
            admission_date        = datetime(2024, 1, 10, 8, 30, 0),
            is_active             = True,
        )
        session.add(patient)
        id_map[pid] = pid

    session.commit()
    print(f"  Patients: {len(id_map)} kayit islendi.")
    return id_map


def seed_vitals(session, patient_ids: set):
    if not os.path.exists(VITALS_PATH):
        print(f"  UYARI: {VITALS_PATH} bulunamadi, vitals atlanıyor.")
        return

    existing_count = session.query(VitalMeasurement).count()
    if existing_count > 0:
        print(f"  VitalMeasurement tablosu zaten dolu ({existing_count} kayit), atlanıyor.")
        return

    print(f"  all_vitals.csv okunuyor...")
    batch = []
    total = 0

    with open(VITALS_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["patientId"]
            if pid not in patient_ids:
                continue

            batch.append(VitalMeasurement(
                measurement_id        = str(uuid.uuid4()),
                patient_id            = pid,
                stream_id             = None,
                signal_type           = row["signalType"],
                value                 = float(row["value"]),
                timestamp             = parse_dt(row["timestamp"]),
                timestamp_sec         = float(row["timestamp_sec"]),
                is_valid              = row["isValid"].strip().lower() == "true",
                gestational_age_weeks = int(row["gestationalAgeWeeks"]),
                postnatal_age_days    = int(row["postnatalAgeDays"]),
                pma_weeks             = float(row["pma_weeks"]),
                label_sepsis          = int(row["label_sepsis"]),
                label_apnea           = int(row["label_apnea"]),
                label_cardiac         = int(row["label_cardiac"]),
                label_healthy         = int(row["label_healthy"]),
            ))

            if len(batch) >= BATCH_SIZE:
                session.bulk_save_objects(batch)
                session.commit()
                total += len(batch)
                batch = []
                print(f"    {total} satir yazildi...")

    if batch:
        session.bulk_save_objects(batch)
        session.commit()
        total += len(batch)

    print(f"  VitalMeasurement: {total} kayit yazildi.")


def main():
    if not os.path.exists(METADATA_PATH):
        print(f"HATA: {METADATA_PATH} bulunamadi.")
        print("Once generator.py ile veri uretmelisin.")
        sys.exit(1)

    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    patients_meta = metadata["patients"]
    print(f"Seed basliyor — {len(patients_meta)} hasta...")

    session = SessionLocal()
    try:
        id_map = seed_patients(session, patients_meta)
        seed_vitals(session, set(id_map.keys()))
        print("\nSeed tamamlandi.")
    except Exception as e:
        session.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()