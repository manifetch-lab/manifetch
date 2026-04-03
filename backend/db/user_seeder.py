from passlib.context import CryptContext
from backend.db.base import SessionLocal
from backend.db.models import User
from backend.db.enums import Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_USERS = [
    {
        "username":     "dr_ayse",
        "password":     "Doctor123!",
        "role":         Role.DOCTOR,
        "display_name": "Dr. Ayse Kaya",
    },
    {
        "username":     "nurse_mehmet",
        "password":     "Nurse123!",
        "role":         Role.NURSE,
        "display_name": "Hemşire Mehmet Demir",
    },
    {
        "username":     "admin",
        "password":     "Admin123!",
        "role":         Role.ADMINISTRATOR,
        "display_name": "Sistem Yöneticisi",
    },
]


def seed_users():
    db = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing > 0:
            print(f"Users tablosu zaten dolu ({existing} kullanici), atlanıyor.")
            return

        print("Test kullanıcıları oluşturuluyor...")
        for u in TEST_USERS:
            user = User(
                username      = u["username"],
                password_hash = pwd_context.hash(u["password"]),
                role          = u["role"].value,
                display_name  = u["display_name"],
                is_active     = True,
            )
            db.add(user)

        db.commit()
        print(f"Toplam {len(TEST_USERS)} kullanici olusturuldu.")
        print()
        for u in TEST_USERS:
            print(f"  {u['role'].value:<15}  kullanici: {u['username']:<15}  sifre: {u['password']}")

    except Exception as e:
        db.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()