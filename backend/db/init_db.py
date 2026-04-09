import argparse
import json
import os
import sys

from backend.db.base import engine, Base, SessionLocal
from backend.db import models  # noqa: F401
from backend.db.seed import seed_patients, seed_vitals, METADATA_PATH
from backend.db.threshold_seeder import seed_thresholds
from backend.db.user_seeder import seed_users


def init_db(no_vitals: bool = False):
    print("Tablolar kontrol ediliyor...")
    Base.metadata.create_all(bind=engine)
    print("Tablolar hazir.")
    print()

    print("=== Kullanici Seed ===")
    seed_users()
    print()

    # Hasta seed (her zaman)
    print("=== Hasta Seed ===")
    if not os.path.exists(METADATA_PATH):
        print(f"HATA: {METADATA_PATH} bulunamadi.")
        print("Once generator.py ile veri uretmelisin.")
        sys.exit(1)

    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    session = SessionLocal()
    try:
        id_map = seed_patients(session, metadata["patients"])
    finally:
        session.close()
    print()

    # Vital seed (opsiyonel)
    if no_vitals:
        print("=== Vital Measurements Seed ===")
        print("  --no-vitals aktif, atlanıyor (publisher ile gelecek)")
        print()
    else:
        print("=== Vital Measurements Seed ===")
        session = SessionLocal()
        try:
            seed_vitals(session, set(id_map.keys()))
        finally:
            session.close()
        print()

    print("=== Threshold Seed ===")
    seed_thresholds()
    print()

    print("=== Veritabani hazir ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manifetch DB init")
    parser.add_argument("--no-vitals", action="store_true",
                        help="Vital measurement seed'ini atla (demo icin — publisher ile gelecek)")
    args = parser.parse_args()
    init_db(no_vitals=args.no_vitals)