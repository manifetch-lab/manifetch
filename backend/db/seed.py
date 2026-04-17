import json
import csv
import os
import sys
import uuid
from datetime import datetime, timezone
from backend.db.base import SessionLocal, engine
from backend.db.models import Base, Patient, VitalMeasurement
from backend.db.enums import SignalType

DATA_DIR      = os.path.join(os.path.dirname(__file__), "..", "..", "data", "all_data")
METADATA_PATH = os.path.join(DATA_DIR, "patients_metadata.json")
VITALS_PATH   = os.path.join(DATA_DIR, "all_vitals.csv")

BATCH_SIZE = 5000

SIGNAL_UNITS = {
    SignalType.HEART_RATE.value: "BPM",
    SignalType.SPO2.value:       "%",
    SignalType.RESP_RATE.value:  "breaths/min",
    SignalType.ECG.value:        "mV",
}


def parse_dt(s: str) -> datetime:
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def seed_patients(session, patients_meta: list) -> dict:
    id_map   = {}
    existing = {p.patient_id for p in session.query(Patient.patient_id).all()}

    for p in patients_meta:
        pid = p["patientId"]
        if pid in existing:
            id_map[pid] = pid
            continue

        patient = Patient(
            patient_id            = pid,
            gestational_age_weeks = p["gestationalAgeWeeks"],
            postnatal_age_days    = p["postnatalAgeDays"],
            admission_date        = datetime(2024, 1, 10, 8, 30, 0, tzinfo=timezone.utc),
            is_active             = True,
        )
        patient.full_name = f"Simulated Patient {pid[:8]}"  # setter → şifreli
        session.add(patient)
        id_map[pid] = pid

    session.commit()
    print(f"  Patients: {len(id_map)} kayıt işlendi.")
    return id_map


def seed_vitals(session, patient_ids: set):
    if not os.path.exists(VITALS_PATH):
        print(f"  UYARI: {VITALS_PATH} bulunamadı, vitals atlanıyor.")
        return

    existing_count = session.query(VitalMeasurement).count()
    if existing_count > 0:
        print(f"  VitalMeasurement tablosu zaten dolu ({existing_count} kayıt), atlanıyor.")
        return

    print("  all_vitals.csv okunuyor...")
    batch = []
    total = 0

    with open(VITALS_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["patientId"]
            if pid not in patient_ids:
                continue

            signal_type = row["signalType"]
            unit        = SIGNAL_UNITS.get(signal_type, "")

            batch.append(VitalMeasurement(
                measurement_id        = str(uuid.uuid4()),
                patient_id            = pid,
                stream_id             = None,
                signal_type           = signal_type,
                value                 = float(row["value"]),
                unit                  = unit,
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
                print(f"    {total:,} satır yazıldı...")

    if batch:
        session.bulk_save_objects(batch)
        session.commit()
        total += len(batch)

    print(f"  VitalMeasurement: {total:,} kayıt yazıldı.")


def main():
    # DÜZELTME: Kazara çalıştırmaya karşı onay sorusu
    print("=" * 60)
    print("UYARI: Bu script tüm simüle veriyi DB'ye yazar.")
    print("Yüz binlerce satır yazılabilir. Emin misiniz?")
    print("=" * 60)
    confirm = input("Devam etmek için 'evet' yazın: ").strip().lower()
    if confirm != "evet":
        print("İptal edildi.")
        sys.exit(0)

    if not os.path.exists(METADATA_PATH):
        print(f"HATA: {METADATA_PATH} bulunamadı.")
        print("Önce generator.py ile veri üretmelisin.")
        sys.exit(1)

    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    patients_meta = metadata["patients"]
    print(f"Seed başlıyor — {len(patients_meta)} hasta...")

    session = SessionLocal()
    try:
        id_map = seed_patients(session, patients_meta)
        seed_vitals(session, set(id_map.keys()))
        print("\nSeed tamamlandı.")
    except Exception as e:
        session.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()