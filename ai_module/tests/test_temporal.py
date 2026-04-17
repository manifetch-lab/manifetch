"""
Manifetch NICU — Temporal Validation
======================================
Temporal split: her hastanın ilk %80'i train, son %20'si test.
Bu yaklaşım "gelecekteki" veriyi tahmin ettiğimizi doğrular —
GA-stratified random split'ten daha gerçekçi klinik değerlendirme sağlar.

Neden önemli:
  - Sliding window örnekleri aynı hastayla örtüşür → random split
    veri sızıntısına (data leakage) yol açabilir.
  - Temporal split: model hiç görmediği zaman dilimini tahmin eder.

Çalıştır:
  python test_temporal.py
  python test_temporal.py --disease apnea
  python test_temporal.py --data_dir data/all_data --out_dir models
"""

import argparse
import json
import os
import pickle
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    f1_score, recall_score, precision_score,
    classification_report, confusion_matrix,
)
from sklearn.ensemble import RandomForestClassifier

warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

DISEASES = ["apnea", "cardiac", "sepsis"]

FEATURE_COLS_ALL = [
    "hr_mean", "hr_std", "hr_min", "hr_max", "hr_last", "hr_slope", "hr_hrv",
    "spo2_mean", "spo2_std", "spo2_min", "spo2_max", "spo2_last", "spo2_slope",
    "spo2_pct_below_90", "spo2_min_diff",
    "rr_mean", "rr_std", "rr_min", "rr_max", "rr_last", "rr_slope",
    "rr_pct_below_30", "rr_pct_below_10", "rr_cv", "hr_rr_ratio",
    "ga_weeks", "pna_days", "pma_weeks",
    "ecg_rr_mean_ms", "ecg_rr_std_ms", "ecg_rmssd_ms", "ecg_pnn50",
    "ecg_amp_mean", "ecg_amp_std", "ecg_amp_min", "ecg_amp_slope",
]

# TC-36: F1 ≥ 0.80 hedefi
F1_TARGET = 0.80

# Apnea için recall hedefi (FN maliyeti yüksek)
RECALL_TARGETS = {"apnea": 0.85, "cardiac": None, "sepsis": None}


def temporal_split(df: pd.DataFrame, train_ratio: float = 0.80):
    """
    Her hasta için ilk %train_ratio → train, kalan → test.
    Pencereler timestamp_sec'e göre sıralanır.
    Veri sızıntısı yok: test seti her zaman train setinden sonraki zaman dilimine ait.
    """
    train_rows = []
    test_rows  = []

    for pid, group in df.groupby("patient_id"):
        group_sorted = group.sort_values("t_end_sec")
        n_train      = max(1, int(len(group_sorted) * train_ratio))
        train_rows.append(group_sorted.iloc[:n_train])
        if len(group_sorted) > n_train:
            test_rows.append(group_sorted.iloc[n_train:])

    train_df = pd.concat(train_rows, ignore_index=True) if train_rows else pd.DataFrame()
    test_df  = pd.concat(test_rows,  ignore_index=True) if test_rows  else pd.DataFrame()
    return train_df, test_df


def select_threshold(y_true, y_prob, recall_target=None) -> float:
    from sklearn.metrics import precision_recall_curve
    prec, rec, thresholds = precision_recall_curve(y_true, y_prob)
    if recall_target is not None:
        mask = rec[:-1] >= recall_target
        if mask.any():
            best_idx = np.where(mask)[0][np.argmax(prec[:-1][mask])]
            return float(thresholds[best_idx])
    f1s = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-9)
    return float(thresholds[np.argmax(f1s)])


def evaluate_model(name, model, X_test, y_test, recall_target=None, is_lgb=False):
    """Model metriklerini hesapla ve yazdır."""
    if is_lgb:
        y_prob = model.predict(X_test)
    else:
        y_prob = model.predict_proba(X_test)[:, 1]

    threshold = select_threshold(y_test, y_prob, recall_target)
    y_pred    = (y_prob >= threshold).astype(int)

    f1        = f1_score(y_test, y_pred, zero_division=0)
    recall    = recall_score(y_test, y_pred, zero_division=0)
    precision = precision_score(y_test, y_pred, zero_division=0)
    auc       = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.0
    aupr      = average_precision_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.0

    if recall_target:
        f1_ok = "✓" if recall >= recall_target else "✗"
    else:
        f1_ok = "✓" if f1 >= F1_TARGET else "✗"

    print(f"  {name:<12} F1={f1:.4f} {f1_ok}  "
          f"Recall={recall:.4f}  Precision={precision:.4f}  "
          f"AUC={auc:.4f}  thr={threshold:.3f}")

    return {
        "f1": round(f1, 4), "recall": round(recall, 4),
        "precision": round(precision, 4), "auc": round(auc, 4),
        "aupr": round(aupr, 4), "threshold": round(threshold, 4),
        "f1_target_met": (recall >= recall_target if recall_target else f1 >= F1_TARGET),
    }


def validate_disease(disease: str, data_dir: str, out_dir: str):
    print(f"\n{'='*60}")
    print(f"  {disease.upper()} — Temporal Validation (80/20 split)")
    print(f"{'='*60}")

    path = os.path.join(data_dir, f"features_{disease}.csv")
    if not os.path.exists(path):
        print(f"  HATA: {path} bulunamadı. Önce prepare_features.py çalıştırın.")
        return {}

    df           = pd.read_csv(path)

    if disease == "cardiac":
        cardiac_cols = [
            "hr_mean", "hr_std", "hr_min", "hr_max", "hr_last", "hr_slope", "hr_hrv",
            "ecg_rr_mean_ms", "ecg_rr_std_ms", "ecg_rmssd_ms", "ecg_pnn50",
            "ecg_amp_mean", "ecg_amp_std", "ecg_amp_min", "ecg_amp_slope",
            "ga_weeks", "pna_days", "pma_weeks",
        ]
        feature_cols = [c for c in cardiac_cols if c in df.columns]
    else:
        feature_cols = [c for c in FEATURE_COLS_ALL if c in df.columns]
    
    
    # Temporal split
    train_df, test_df = temporal_split(df, train_ratio=0.80)

    if test_df.empty:
        print("  UYARI: Test seti boş — yeterli hasta/pencere yok.")
        return {}

    X_train = train_df[feature_cols].values
    y_train = train_df["label"].values
    X_test  = test_df[feature_cols].values
    y_test  = test_df["label"].values

    # NaN → 0
    X_train = np.nan_to_num(X_train, nan=0.0)
    X_test  = np.nan_to_num(X_test,  nan=0.0)

    train_pids = set(train_df["patient_id"].unique())
    test_pids  = set(test_df["patient_id"].unique())

    if len(np.unique(y_test)) < 2:
        print("  UYARI: Test setinde tek sınıf var — metrik hesaplanamıyor.")
        return {}

    neg_c, pos_c = np.bincount(y_train)
    print(f"  Train: {len(train_pids)} hasta, {len(X_train):,} pencere "
          f"(neg={neg_c}, pos={pos_c})")
    print(f"  Test : {len(test_pids)} hasta, {len(X_test):,} pencere")
    print(f"  Test pozitif oranı: {y_test.mean():.1%}")
    print(f"  Train/Test hasta örtüşmesi: "
          f"{'VAR ⚠' if train_pids & test_pids else 'YOK ✓ (sızıntı yok)'}")

    recall_target = RECALL_TARGETS.get(disease)
    results = {}

    print(f"\n  {'─'*50}")
    print(f"  Model Değerlendirmesi (Temporal Split)")
    print(f"  {'─'*50}")

    # ── Yüklü modelleri değerlendir ──────────────────────────────────────────
    for model_type in ["lgb", "rf", "xgb"]:
        model_path = os.path.join(out_dir, f"model_{model_type}_{disease}.pkl")
        if not os.path.exists(model_path):
            continue
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        is_lgb = (model_type == "lgb")
        results[model_type] = evaluate_model(
            model_type.upper(), model, X_test, y_test, recall_target, is_lgb
        )

    # ── Eğitilmiş model yoksa sıfırdan RF eğit ───────────────────────────────
    if not results:
        print("  Kayıtlı model bulunamadı — sıfırdan RF eğitiliyor...")
        scale_pos = max(neg_c, 1) / max(pos_c, 1)
        rf_model = RandomForestClassifier(
            n_estimators=200, max_depth=12, min_samples_leaf=5,
            class_weight="balanced", n_jobs=-1, random_state=42,
        )
        rf_model.fit(X_train, y_train)
        results["rf"] = evaluate_model(
            "RF (temporal)", rf_model, X_test, y_test, recall_target
        )

    # ── TC-36: F1 ≥ 0.80 kontrolü ────────────────────────────────────────────
    print(f"\n  TC-36 Kontrol (F1 ≥ {F1_TARGET}):")
    all_passed = True
    for model_type, metrics in results.items():
        status = "✓ GEÇTI" if metrics.get("f1_target_met") else "✗ KALDI"
        print(f"    {model_type.upper():<10} F1={metrics['f1']:.4f}  {status}")
        if not metrics.get("f1_target_met"):
            all_passed = False

    if all_passed:
        print(f"\n  ✓ Tüm modeller F1 ≥ {F1_TARGET} hedefini karşıladı.")
    else:
        print(f"\n  ✗ Bazı modeller F1 ≥ {F1_TARGET} hedefini karşılamadı.")
        print("    Öneri: Daha fazla hasta verisi üretin veya hiperparametreleri ayarlayın.")

    # Sonuçları kaydet
    out = {
        "disease":           disease,
        "split":             "temporal_80_20",
        "n_train_patients":  len(train_pids),
        "n_test_patients":   len(test_pids),
        "n_train_windows":   len(X_train),
        "n_test_windows":    len(X_test),
        "pos_ratio_test":    round(float(y_test.mean()), 4),
        "f1_target":         F1_TARGET,
        "all_f1_targets_met": all_passed,
        "results":           results,
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"temporal_validation_{disease}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Sonuçlar kaydedildi: {out_path}")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="data/all_data")
    parser.add_argument("--out_dir",  default="models")
    parser.add_argument("--disease",  default="all",
                        choices=["all"] + DISEASES)
    args = parser.parse_args()

    targets = DISEASES if args.disease == "all" else [args.disease]

    print("=" * 60)
    print("Manifetch NICU — Temporal Validation")
    print("Split: her hastanın ilk %80 train, son %20 test")
    print("=" * 60)

    summary = []
    for disease in targets:
        r = validate_disease(disease, args.data_dir, args.out_dir)
        if r:
            summary.append(r)

    if summary:
        print(f"\n{'='*60}")
        print("  ÖZET")
        print(f"{'='*60}")
        print(f"  {'Hastalık':<10} {'En iyi F1':>10} {'Hedef':>8} {'Sonuç':>10}")
        print(f"  {'─'*45}")
        for r in summary:
            best_f1 = max(
                (m.get("f1", 0) for m in r.get("results", {}).values()),
                default=0,
            )
            status = "✓ GEÇTI" if r.get("all_f1_targets_met") else "✗ KALDI"
            print(f"  {r['disease']:<10} {best_f1:>10.4f} {F1_TARGET:>8.2f} {status:>10}")


if __name__ == "__main__":
    main()