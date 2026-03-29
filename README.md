# Manifetch NICU Monitoring System

Web tabanlı neonatal yoğun bakım izleme platformu.

## Gereksinimler

- Python 3.10+
- PostgreSQL 15+

## Kurulum

### 1. Repoyu clone'la
```bash
git clone https://github.com/kullaniciadi/manifetch.git
cd manifetch_project
```

### 2. Virtual environment oluştur
```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

### 3. Bağımlılıkları kur
```bash
pip install -e .
```

### 4. .env dosyasını oluştur
```bash
cp .env.example .env
```

`.env` dosyasını aç ve şu değerleri doldur:

- `DB_PASSWORD` — PostgreSQL şifresi
- `DB_HOST` — server IP adresi (ekip arkadaşından al)
- `MANIFETCH_SECRET_KEY` — şifreleme anahtarı (ekip arkadaşından al)

### 5. Veritabanını kur
```bash
alembic upgrade head
python backend/db/init_db.py
```

### 6. Sunucuyu başlat
```bash
uvicorn backend.main:app --reload
```

API dokümantasyonu: http://localhost:8000/docs

## Proje Yapısı
```
manifetch_project/
├── backend/
│   ├── api/          # HTTP endpoint'leri
│   ├── db/           # Veritabanı katmanı
│   │   ├── models.py
│   │   ├── base.py
│   │   ├── enums.py
│   │   ├── encryption.py
│   │   ├── seed.py
│   │   ├── threshold_seeder.py
│   │   ├── user_seeder.py
│   │   └── init_db.py
│   ├── services/     # İş mantığı
│   │   ├── rule_engine_service.py
│   │   └── alert_service.py
│   └── main.py
├── data/             # Üretilen veriler (Git'e gitmez)
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Test Kullanıcıları

| Rol | Kullanıcı Adı | Şifre |
|-----|---------------|-------|
| Doctor | dr_ayse | Doctor123! |
| Nurse | nurse_mehmet | Nurse123! |
| Administrator | admin | Admin123! |

## Ekip

- Database & Backend: 
- AI Modülü: 
- Frontend: