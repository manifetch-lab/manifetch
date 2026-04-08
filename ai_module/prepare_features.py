"""
Manifetch NICU — Feature Hazırlama
===================================
all_vitals.csv → sliding window → feature vektörleri → 3 ayrı CSV

Pencere boyutları (inference_service.py ile eşleşiyor):
  Apnea:   X=1200s (20dk), Y=300s  (5dk),  adım=30s
  Cardiac: X=1800s (30dk), Y=900s  (15dk), adım=60s
  Sepsis:  X=3600s (60dk), Y=3600s (60dk), adım=60s

Düzeltmeler:
  - Label tüm sinyal türlerinden alınıyor (sadece HR'dan değil)
  - iterrows() → vektörize numpy işlemleri (performans)
"""

import argparse
import os
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

ECG_HZ = 25

CONFIGS = {
    "apnea":   {"x_sec": 1200, "y_sec": 300,  "step_sec": 30},   # inference_service ile eşleşiyor
    "cardiac": {"x_sec": 1800, "y_sec": 900,  "step_sec": 60},
    "sepsis":  {"x_sec": 3600, "y_sec": 3600, "step_sec": 60},
}


# ── ECG beat ekstraksiyon ─────────────────────────────────────────────────────

def extract_ecg_beats(ecg_mv: np.ndarray, fs: int = ECG_HZ) -> pd.DataFrame:
    height_thr = np.percentile(ecg_mv, 80)
    min_dist   = max(3, int(fs * 60 / 300))
    peaks, _   = find_peaks(ecg_mv, height=height_thr, distance=min_dist)

    if len(peaks) < 2:
        return pd.DataFrame(columns=["timestamp_sec", "rr_interval_ms", "r_amplitude"])

    rr_ms = np.diff(peaks) / fs * 1000.0
    rows  = [
        {
            "timestamp_sec":  round(peaks[i + 1] / fs, 4),
            "rr_interval_ms": round(float(rr_ms[i]), 2),
            "r_amplitude":    round(float(ecg_mv[peaks[i + 1]]), 4),
        }
        for i in range(len(rr_ms))
    ]
    return pd.DataFrame(rows)


def load_ecg_beats(pid: str, data_dir: str) -> pd.DataFrame | None:
    beats_path = os.path.join(data_dir, f"ecg_beats_{pid[:8]}.csv")
    if os.path.exists(beats_path):
        return pd.read_csv(beats_path)

    ecg_path = os.path.join(data_dir, f"ecg_{pid[:8]}.csv")
    if not os.path.exists(ecg_path):
        return None

    print(f"    ECG beats çıkarılıyor: {pid[:8]}...", end=" ", flush=True)
    ecg_df = pd.read_csv(ecg_path, usecols=["timestamp_sec", "ecg_mv"])
    beats  = extract_ecg_beats(ecg_df["ecg_mv"].values)
    beats["patient_id"] = pid
    beats.to_csv(beats_path, index=False)
    print(f"{len(beats):,} beat")
    return beats


def ecg_window_features(beats: pd.DataFrame, t_start: float, t_end: float) -> dict:
    w   = beats[(beats["timestamp_sec"] >= t_start) & (beats["timestamp_sec"] < t_end)]
    nan8 = {k: np.nan for k in [
        "ecg_rr_mean_ms", "ecg_rr_std_ms", "ecg_rmssd_ms", "ecg_pnn50",
        "ecg_amp_mean", "ecg_amp_std", "ecg_amp_min", "ecg_amp_slope",
    ]}
    if len(w) < 5:
        return nan8

    rr      = w["rr_interval_ms"].values
    amp     = w["r_amplitude"].values
    rr_diff = np.abs(np.diff(rr))
    rmssd   = float(np.sqrt(np.mean(rr_diff**2))) if len(rr_diff) > 0 else np.nan
    pnn50   = float(np.mean(rr_diff > 50))         if len(rr_diff) > 0 else np.nan
    slope   = float(np.polyfit(np.arange(len(amp)), amp, 1)[0]) if len(amp) > 1 else 0.0

    return {
        "ecg_rr_mean_ms": float(np.mean(rr)),
        "ecg_rr_std_ms":  float(np.std(rr)),
        "ecg_rmssd_ms":   rmssd,
        "ecg_pnn50":      pnn50,
        "ecg_amp_mean":   float(np.mean(amp)),
        "ecg_amp_std":    float(np.std(amp)),
        "ecg_amp_min":    float(np.min(amp)),
        "ecg_amp_slope":  slope,
    }


# ── Vital sign feature ekstraksiyon ──────────────────────────────────────────

def extract_features(hr: np.ndarray, spo2: np.ndarray, rr: np.ndarray) -> dict:
    feats = {}
    for name, arr in [("hr", hr), ("spo2", spo2), ("rr", rr)]:
        clean = arr[~np.isnan(arr)]
        if len(clean) == 0:
            for s in ["mean", "std", "min", "max", "last", "slope"]:
                feats[f"{name}_{s}"] = np.nan
            continue
        feats[f"{name}_mean"]  = float(np.mean(clean))
        feats[f"{name}_std"]   = float(np.std(clean))
        feats[f"{name}_min"]   = float(np.min(clean))
        feats[f"{name}_max"]   = float(np.max(clean))
        feats[f"{name}_last"]  = float(clean[-1])
        feats[f"{name}_slope"] = (
            float(np.polyfit(np.arange(len(clean)), clean, 1)[0])
            if len(clean) > 1 else 0.0
        )

    spo2_c = spo2[~np.isnan(spo2)]
    feats["spo2_pct_below_90"] = float(np.mean(spo2_c < 90)) if len(spo2_c) > 0 else np.nan
    feats["spo2_min_diff"]     = float(np.min(np.diff(spo2_c))) if len(spo2_c) > 1 else np.nan

    hr_c = hr[~np.isnan(hr)]
    feats["hr_hrv"] = float(np.std(hr_c)) if len(hr_c) > 0 else np.nan

    rr_c    = rr[~np.isnan(rr)]
    rr_mean = float(np.mean(rr_c)) if len(rr_c) > 0 else 1.0
    hr_mean = feats.get("hr_mean") or 0.0

    feats["rr_pct_below_30"] = float(np.mean(rr_c < 30)) if len(rr_c) > 0 else np.nan
    feats["rr_pct_below_10"] = float(np.mean(rr_c < 10)) if len(rr_c) > 0 else np.nan
    feats["rr_cv"]           = float(np.std(rr_c) / max(rr_mean, 1.0)) if len(rr_c) > 0 else np.nan
    feats["hr_rr_ratio"]     = float(hr_mean / max(rr_mean, 1.0)) if len(rr_c) > 0 else np.nan

    return feats


# ── Pencere oluşturma ─────────────────────────────────────────────────────────

def build_windows(
    patient_df: pd.DataFrame,
    disease:    str,
    x_sec:      int,
    y_sec:      int,
    step_sec:   int,
    beats_df:   pd.DataFrame | None = None,
) -> list[dict]:
    """
    Tek hasta için sliding window örnekleri.

    DÜZELTME 1: iterrows() kaldırıldı — pivot + numpy ile vektörize.
    DÜZELTME 2: Label tüm sinyal türlerinden alınıyor (sadece HR değil).
    """
    label_col = f"label_{disease}"
    max_sec   = int(patient_df["timestamp_sec"].max())

    # Vektörize pivot: her saniye için HR, SpO2, RR dizileri
    hr_arr   = np.full(max_sec + 1, np.nan)
    spo2_arr = np.full(max_sec + 1, np.nan)
    rr_arr   = np.full(max_sec + 1, np.nan)

    # DÜZELTME: label_arr tüm sinyal satırlarından OR alınıyor
    lbl_arr  = np.zeros(max_sec + 1, dtype=np.int8)

    # Pivot — signal type bazında tek geçişte doldur
    for sig_type, target_arr in [
        ("HEART_RATE", hr_arr),
        ("SPO2",       spo2_arr),
        ("RESP_RATE",  rr_arr),
    ]:
        sig_df = patient_df[patient_df["signalType"] == sig_type]
        if sig_df.empty:
            continue
        idx = sig_df["timestamp_sec"].astype(int).clip(0, max_sec).values
        target_arr[idx] = sig_df["value"].values

        # Label: bu sinyal tipinden gelen satırlarda label=1 varsa işaretle
        if label_col in sig_df.columns:
            lbl_arr[idx] = np.maximum(
                lbl_arr[idx],
                sig_df[label_col].values.astype(np.int8),
            )

    # Hasta metadata
    ga_weeks  = patient_df["gestationalAgeWeeks"].iloc[0]
    pna_days  = patient_df["postnatalAgeDays"].iloc[0]
    pma_weeks = patient_df["pma_weeks"].iloc[0]
    patient_id = patient_df["patientId"].iloc[0]

    samples = []
    for t_end in range(x_sec, max_sec - y_sec + 1, step_sec):
        t_start = t_end - x_sec

        hr_w   = hr_arr[t_start:t_end]
        spo2_w = spo2_arr[t_start:t_end]
        rr_w   = rr_arr[t_start:t_end]

        if np.all(np.isnan(hr_w)):
            continue

        feats = extract_features(hr_w, spo2_w, rr_w)

        if beats_df is not None:
            ecg_feats = ecg_window_features(beats_df, float(t_start), float(t_end))
            feats.update(ecg_feats)

        future_labels = lbl_arr[t_end: t_end + y_sec]
        label = int(np.any(future_labels == 1))

        feats["label"]      = label
        feats["t_end_sec"]  = t_end
        feats["patient_id"] = patient_id
        feats["ga_weeks"]   = ga_weeks
        feats["pna_days"]   = pna_days
        feats["pma_weeks"]  = pma_weeks

        samples.append(feats)

    return samples


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",      default="data/all_data/all_vitals.csv")
    parser.add_argument("--output_dir", default="data/all_data")
    parser.add_argument("--no_ecg",     action="store_true",
                        help="ECG özelliklerini atla (hızlı test için)")
    args = parser.parse_args()

    print("Veri yükleniyor...")
    df       = pd.read_csv(args.input)
    patients = df["patientId"].unique()
    print(f"{len(patients)} hasta, {len(df):,} satır")

    use_ecg = not args.no_ecg

    for disease, cfg in CONFIGS.items():
        print(f"\n--- {disease.upper()} "
              f"(X={cfg['x_sec']}s, Y={cfg['y_sec']}s, adım={cfg['step_sec']}s) ---")
        all_samples = []

        for pid in patients:
            pdata  = df[df["patientId"] == pid].copy()
            beats  = load_ecg_beats(pid, args.output_dir) if use_ecg else None
            samples = build_windows(
                pdata, disease,
                cfg["x_sec"], cfg["y_sec"], cfg["step_sec"],
                beats_df=beats,
            )
            all_samples.extend(samples)
            print(f"  {pid[:8]}: {len(samples)} pencere")

        out_df = pd.DataFrame(all_samples)
        if out_df.empty:
            print(f"  UYARI: {disease} için örnek üretilemedi.")
            continue

        pos = int(out_df["label"].sum())
        neg = len(out_df) - pos
        print(f"  Toplam: {len(out_df):,} pencere | "
              f"pozitif={pos} ({pos/len(out_df):.1%}), negatif={neg}")

        out_path = os.path.join(args.output_dir, f"features_{disease}.csv")
        out_df.to_csv(out_path, index=False)
        print(f"  Kaydedildi: {out_path}")

    print("\nTamamlandı.")


if __name__ == "__main__":
    main()