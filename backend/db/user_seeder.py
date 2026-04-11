import os
from passlib.context import CryptContext
from backend.db.base import SessionLocal
from backend.db.models import User
from backend.db.enums import Role
from dotenv import load_dotenv
load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_users():
    for key in ["SEED_DOCTOR_PASSWORD", "SEED_NURSE_PASSWORD", "SEED_ADMIN_PASSWORD"]:
        if not os.getenv(key):
            raise ValueError(f"{key} environment variable ayarlanmamış.")

    test_users = [
        {
            "username":     "dr_ayse",
            "password":     os.getenv("SEED_DOCTOR_PASSWORD"),
            "role":         Role.DOCTOR,
            "display_name": "Dr. Ayşe Kaya",
        },
        {
            "username":     "nurse_mehmet",
            "password":     os.getenv("SEED_NURSE_PASSWORD"),
            "role":         Role.NURSE,
            "display_name": "Hemşire Mehmet Demir",
        },
        {
            "username":     "admin",
            "password":     os.getenv("SEED_ADMIN_PASSWORD"),
            "role":         Role.ADMINISTRATOR,
            "display_name": "Sistem Yöneticisi",
        },
    ]

    db = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing > 0:
            print(f"Users tablosu zaten dolu ({existing} kullanıcı), atlanıyor.")
            return

        print("Test kullanıcıları oluşturuluyor...")
        for u in test_users:
            user = User(
                username      = u["username"],
                password_hash = pwd_context.hash(u["password"]),
                role          = u["role"].value,
                is_active     = True,
            )
            user.display_name = u["display_name"]
            db.add(user)

        db.commit()
        print(f"Toplam {len(test_users)} kullanıcı oluşturuldu.")

    except Exception as e:
        db.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()