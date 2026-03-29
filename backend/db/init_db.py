from backend.db.base import engine, Base
from backend.db import models  # noqa: F401
from backend.db.seed import main as seed_vitals
from backend.db.threshold_seeder import seed_thresholds
from backend.db.user_seeder import seed_users


def init_db():
    print("Tablolar kontrol ediliyor...")
    Base.metadata.create_all(bind=engine)
    print("Tablolar hazir.")
    print()

    print("=== Kullanici Seed ===")
    seed_users()
    print()

    print("=== Threshold Seed ===")
    seed_thresholds()
    print()

    print("=== Vital Measurements Seed ===")
    seed_vitals()
    print()

    print("=== Veritabani hazir ===")


if __name__ == "__main__":
    init_db()