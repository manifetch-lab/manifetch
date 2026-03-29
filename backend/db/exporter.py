import os
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from backend.db.base import engine

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "parquet")


def export_vitals_to_parquet(
    patient_id: str = None,
    signal_type: str = None,
    days_back: int = None,
    filename: str = None,
):
    os.makedirs(EXPORT_DIR, exist_ok=True)

    query = "SELECT * FROM vital_measurements WHERE 1=1"
    params = {}

    if patient_id:
        query += " AND patient_id = :patient_id"
        params["patient_id"] = patient_id

    if signal_type:
        query += " AND signal_type = :signal_type"
        params["signal_type"] = signal_type

    if days_back:
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        query += " AND timestamp >= :cutoff"
        params["cutoff"] = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    query += " ORDER BY patient_id, timestamp"

    print(f"Veri okunuyor...")
    df = pd.read_sql(text(query), engine, params=params)
    print(f"  {len(df):,} satir okundu.")

    if df.empty:
        print("  Kayit bulunamadi, export atlanıyor.")
        return None

    if not filename:
        tag = signal_type.lower() if signal_type else "all"
        ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"vitals_{tag}_{ts}.parquet"

    out_path = os.path.join(EXPORT_DIR, filename)
    df.to_parquet(out_path, index=False, compression="snappy")

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  Kaydedildi: {out_path}")
    print(f"  Dosya boyutu: {size_mb:.1f} MB")
    return out_path


def archive_old_vitals(days: int = 90):
    """
    days gundan eski vital_measurements satirlarini parquet'e yazar ve siler.
    Alert ve ai_results etkilenmez.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    print(f"{days} gundan eski veriler arsivleniyor (kesim: {cutoff.date()})...")

    ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = export_vitals_to_parquet(
        days_back=None,
        filename=f"archive_{ts}.parquet",
    )

    if out is None:
        return

    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM vital_measurements WHERE timestamp < :cutoff"),
            {"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")},
        )
        conn.commit()
        print(f"  {result.rowcount:,} satir silindi.")

    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()
    print("  VACUUM tamamlandi.")


if __name__ == "__main__":
    export_vitals_to_parquet(filename="vitals_full_export.parquet")