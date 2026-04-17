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
    days günden eski vital_measurements satırlarını parquet'e yazar ve siler.
    Alert ve ai_results etkilenmez.

    DÜZELTME: Eski halde days_back=None ile tüm veri export ediliyordu,
    sonra sadece eski satırlar siliniyordu — export ile silme tutarsızdı.
    Şimdi cutoff doğrudan SQL sorgusuna geçiriliyor, sadece eski veri export edilir.
    """
    cutoff     = datetime.utcnow() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{days} günden eski veriler arşivleniyor (kesim: {cutoff.date()})...")

    # DÜZELTME: Sadece cutoff'tan eski satırları export et
    os.makedirs(EXPORT_DIR, exist_ok=True)
    ts    = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    query = "SELECT * FROM vital_measurements WHERE timestamp < :cutoff ORDER BY patient_id, timestamp"

    print("  Eski veriler okunuyor...")
    df = pd.read_sql(text(query), engine, params={"cutoff": cutoff_str})
    print(f"  {len(df):,} satır okundu.")

    if df.empty:
        print("  Arşivlenecek eski kayıt bulunamadı.")
        return

    out_path = os.path.join(EXPORT_DIR, f"archive_{ts}.parquet")
    df.to_parquet(out_path, index=False, compression="snappy")
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  Arşiv kaydedildi: {out_path} ({size_mb:.1f} MB)")

    # Export başarılıysa sil
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM vital_measurements WHERE timestamp < :cutoff"),
            {"cutoff": cutoff_str},
        )
        conn.commit()
        print(f"  {result.rowcount:,} satır silindi.")

    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()
    print("  VACUUM tamamlandı.")


if __name__ == "__main__":
    export_vitals_to_parquet(filename="vitals_full_export.parquet")