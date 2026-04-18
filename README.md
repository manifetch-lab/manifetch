# Manifetch — Real-Time NICU Monitoring Platform

A secure, web-based clinical decision support platform for Neonatal Intensive Care Units (NICU). Monitors simulated neonatal physiological signals in real time and generates AI-assisted risk alerts for healthcare staff.

## Features

- Real-time visualization of neonatal physiological signals (ECG, SpO₂, Heart Rate, Respiration Rate) via WebSocket
- Multi-label AI risk scoring for sepsis, apnea, and cardiac anomaly detection (Random Forest, XGBoost, LightGBM)
- SHAP-based explainability for each AI prediction
- Rule-based threshold evaluation with patient-specific configuration
- Alert lifecycle management: ACTIVE → ACKNOWLEDGED → RESOLVED
- Role-based access control (Doctor, Nurse, Administrator)
- AES-256-GCM encryption for sensitive patient data
- PDF clinical report export
- Historical trend visualization

## Project Structure

```
manifetch/
├── ai_module/          # Inference service, model training, SHAP explainability
├── backend/            # FastAPI backend, PostgreSQL, RBAC, WebSocket
├── data_simulation/    # Synthetic NICU signal generator
├── frontend/           # React frontend
├── tests/              # Integration, unit, and performance tests
├── requirements.txt
└── .env.example
```

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 15+

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd manifetch_project
pip install -r requirements.txt
pip install psycopg2-binary python-jose passlib python-dotenv bcrypt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values. Generate encryption keys with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Required environment variables:

| Variable | Description |
|---|---|
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` | PostgreSQL connection |
| `MANIFETCH_SECRET_KEY` | 64 hex char AES-256 key |
| `MANIFETCH_ENCRYPTION_KEY` | 64 hex char AES-256 key (patient data) |
| `MANIFETCH_JWT_SECRET` | JWT signing secret |
| `SEED_DOCTOR_PASSWORD` | Password for dr_ayse |
| `SEED_NURSE_PASSWORD` | Password for nurse_mehmet |
| `SEED_ADMIN_PASSWORD` | Password for admin |
| `STREAM_USERNAME` | Username for simulation stream |
| `STREAM_PASSWORD` | Password for simulation stream |

### 3. Initialize the database

```bash
# Create the database
python reset_db.py

# Seed users
python -m backend.db.user_seeder
```

### 4. Generate synthetic patient data and seed

```bash
# Generate data
python data_simulation/generator.py --n_patients 20 --duration_hours 24 --output_dir data/all_data --no_ecg

# Seed patients and vitals
echo "evet" | python -m backend.db.seed

# Seed alert thresholds
python -m backend.db.threshold_seeder
```

### 5. Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

### 6. Start the frontend

```bash
cd frontend
npm install
npm start
```

Frontend runs at `http://localhost:3000`. Default users:

| Role | 
|---|---|
| Administrator | 
| Doctor | 
| Nurse | 

Passwords are configured via `SEED_*_PASSWORD` environment variables in `.env`.

## AI Module

### Training pipeline

```bash
# 1. Generate synthetic data
python data_simulation/generator.py --n_patients 200 --duration_hours 24 --output_dir data/all_data --no_ecg

# 2. Extract features
mkdir -p data/features
python ai_module/prepare_features.py --input data/all_data/all_vitals.csv --output_dir data/features --no_ecg

# 3. Train models (RF, XGBoost, LightGBM — best saved per disease)
mkdir -p models_v15
python ai_module/train_model.py --data_dir data/features --out_dir models_v15
```

Pre-trained model files (`.pkl`) are not included in the repository due to size constraints.

### Model performance

| Disease | Model | ROC-AUC | F1 | Recall |
|---|---|---|---|---|
| Apnea | Random Forest | 0.9546 | 0.73 | 0.85 |
| Cardiac | Random Forest | 0.9970 | 0.9958 | 0.9917 |
| Sepsis | LightGBM | 0.9683 | 0.9540 | 0.9196 |

Train/test split is patient-level (GA-stratified, 75/25).

Top SHAP features per disease:

| Disease | Top Features |
|---|---|
| Apnea | `ga_weeks`, `pma_weeks`, `rr_std` |
| Cardiac | `ecg_amp_std`, `ecg_rr_std_ms`, `ecg_amp_mean` |
| Sepsis | `spo2_min_diff`, `rr_pct_below_90`, `rr_std` |

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy ORM, PostgreSQL, Alembic
- **Frontend:** React, Recharts, WebSocket
- **AI/ML:** scikit-learn, XGBoost, LightGBM, SHAP
- **Signal Processing:** NeuroKit2, SciPy
- **Security:** AES-256-GCM, JWT
- **Real-time:** WebSocket (RFC 6455)

## Notes

- This is an academic prototype. AI outputs are decision-support indicators, not medical diagnoses.
- No real patient data is used. All signals are synthetically generated.
- Compliant with KVKK and GDPR regulations.
