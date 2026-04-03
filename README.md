# Manifetch — Real-Time NICU Monitoring Platform

A secure, web-based clinical decision support platform for Neonatal Intensive Care Units (NICU). Monitors simulated neonatal physiological signals in real time and generates AI-assisted risk alerts for healthcare staff.

## Features

- Real-time visualization of neonatal physiological signals (ECG, SpO₂, Heart Rate, Respiration Rate) via WebSocket
- Multi-label AI risk scoring for sepsis, apnea, and cardiac anomaly detection (Random Forest, XGBoost, LightGBM)
- SHAP-based explainability for each AI prediction
- Rule-based threshold evaluation with patient-specific configuration
- Alert lifecycle management: ACTIVE → ACKNOWLEDGED → RESOLVED
- Role-based access control (Doctor, Nurse, Administrator)
- AES-256 encryption for sensitive patient data
- PDF clinical report export
- Historical trend visualization

## Project Structure

```
manifetch/
├── ai_module/          # Inference service, model training, SHAP explainability
├── backend/            # FastAPI backend, PostgreSQL, RBAC, WebSocket
├── data_simulation/    # Synthetic NICU signal generator
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Setup

1. Clone the repository
2. Create a virtual environment and install dependencies:
```bash
pip install -r requirements.txt
```
3. Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```
4. Initialize the database:
```bash
python -m backend.db.init_db
```
5. Start the backend:
```bash
uvicorn backend.main:app --reload
```

## AI Module

Models are trained using `ai_module/train_model.py` on synthetic neonatal data generated via `data_simulation/generator.py`. Pre-trained model files (`.pkl`) are not included in the repository due to size constraints — run the training pipeline to generate them.

```bash
python ai_module/train_model.py --data_dir data --out_dir ai_module/models
```

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, PostgreSQL, Alembic
- **AI/ML:** scikit-learn, XGBoost, LightGBM, SHAP
- **Signal Processing:** NeuroKit2, SciPy
- **Security:** AES-256, TLS 1.3, JWT
- **Real-time:** WebSocket (RFC 6455)

## Notes

- This is an academic prototype. AI outputs are decision-support indicators, not medical diagnoses.
- No real patient data is used. All signals are synthetically generated.
- Compliant with KVKK and GDPR regulations.