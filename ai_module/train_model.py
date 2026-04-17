"""
Manifetch NICU — RF + XGBoost + LightGBM Erken Uyarı Modelleri
================================================================
Her hastalık için ayrı model, 3 algoritma karşılaştırması:
  - Hasta bazlı GA-stratified split (veri sızıntısı yok)
  - Random Forest, XGBoost, LightGBM
  - Apnea: recall≥0.85 hedefi (FN maliyeti yüksek — klinik öncelik)
  - Cardiac, Sepsis: F1-max threshold
  - SHAP açıklanabilirlik (kazanan model)
  - Model ve metrikler kaydedilir

Temporal validation için: test_temporal.py
"""

import argparse
import json
import os
import pickle
import time
import warnings

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    classification_report, confusion_matrix,
    precision_recall_curve, f1_score,
    recall_score, precision_score,
)
from sklearn.model_selection import GroupKFold

warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False
    print("LightGBM bulunamadı: pip install lightgbm")

try:
    from xgboost import XGBClassifier
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    print("XGBoost bulunamadı: pip install xgboost")

DISEASES = ["apnea", "cardiac", "sepsis"]

ECG_FEATURE_COLS = [
    "ecg_rr_mean_ms", "ecg_rr_std_ms", "ecg_rmssd_ms", "ecg_pnn50",
    "ecg_amp_mean", "ecg_amp_std", "ecg_amp_min", "ecg_amp_slope",
]

FEATURE_COLS_ALL = [
    "hr_mean", "hr_std", "hr_min", "hr_max", "hr_last", "hr_slope", "hr_hrv",
    "spo2_mean", "spo2_std", "spo2_min", "spo2_max", "spo2_last", "spo2_slope",
    "spo2_pct_below_90", "spo2_min_diff",
    "rr_mean", "rr_std", "rr_min", "rr_max", "rr_last", "rr_slope",
    "rr_pct_below_30", "rr_pct_below_10", "rr_cv", "hr_rr_ratio",
    "ga_weeks", "pna_days", "pma_weeks",
] + ECG_FEATURE_COLS

# Apnea: recall öncelikli (FN maliyeti yüksek); Cardiac/Sepsis: F1-max
RECALL_TARGETS = {"apnea": 0.85, "cardiac": None, "sepsis": None}

LGBM_PARAMS = {
    "objective":         "binary",
    "metric":            "auc",
    "learning_rate":     0.05,
    "num_leaves":        31,
    "min_child_samples": 20,
    "feature_fraction":  0.8,
    "bagging_fraction":  0.8,
    "bagging_freq":      5,
    "verbose":           -1,
    "n_jobs":            -1,
    "random_state":      42,
}


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────

def safe_bincount(y) -> tuple[int, int]:
    """
    DÜZELTME: np.bincount unpack crash'i önler.
    Eğer y sadece 0'lardan oluşuyorsa pos=0 döner (ZeroDivisionError riski yok).
    """
    counts = np.bincount(y)
    neg = int(counts[0]) if len(counts) > 0 else 0
    pos = int(counts[1]) if len(counts) > 1 else 0
    return neg, pos


def select_threshold(y_true, y_prob, recall_target=None) -> float:
    """F1-max threshold; recall_target verilirse recall >= target koşulunda max precision."""
    prec, rec, thresholds = precision_recall_curve(y_true, y_prob)
    if recall_target is not None:
        mask = rec[:-1] >= recall_target
        if mask.any():
            best_idx = np.where(mask)[0][np.argmax(prec[:-1][mask])]
            return float(thresholds[best_idx])
    f1s = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-9)
    return float(thresholds[np.argmax(f1s)])


def ga_stratified_split(df: pd.DataFrame, groups: np.ndarray):
    """
    Hasta bazlı GA-stratified train/test split.
    DÜZELTME: Train setinde her zaman en az 1 pozitif hasta kalır.
    (test_temporal.py'deki eski versiyonla tutarsızlık giderildi)
    """
    patient_meta = df.groupby("patient_id").agg(
        ga_weeks  = ("ga_weeks", "first"),
        has_label = ("label",    "max"),
    ).reset_index()

    bins = [0, 28, 32, 36, 99]
    patient_meta["ga_group"] = pd.cut(
        patient_meta["ga_weeks"], bins=bins, labels=False
    )

    rng       = np.random.default_rng(42)
    test_pids = set()

    for _, grp in patient_meta.groupby("ga_group"):
        pos    = grp[grp["has_label"] == 1]["patient_id"].values
        neg    = grp[grp["has_label"] == 0]["patient_id"].values
        n_test = max(1, len(grp) // 4)

        # Test'e en fazla (pos-1) pozitif hasta al → train'de en az 1 pozitif kalsın
        max_pos_to_test = max(0, len(pos) - 1)
        n_pos = max(0, min(max_pos_to_test, n_test // 2))
        n_neg = max(0, min(len(neg), n_test - n_pos))

        if n_pos > 0:
            test_pids.update(rng.choice(pos, size=n_pos, replace=False).tolist())
        if n_neg > 0:
            test_pids.update(rng.choice(neg, size=n_neg, replace=False).tolist())

    train_mask = np.array([g not in test_pids for g in groups])
    return train_mask, ~train_mask


def print_metrics(name, y_test, y_prob, threshold, recall_target=None) -> dict:
    """Model metriklerini hesapla ve yazdır."""
    y_pred    = (y_prob >= threshold).astype(int)
    f1        = f1_score(y_test, y_pred, zero_division=0)
    recall    = recall_score(y_test, y_pred, zero_division=0)
    precision = precision_score(y_test, y_pred, zero_division=0)
    auc       = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.0
    aupr      = average_precision_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.0

    thr_label = f"recall≥{recall_target}" if recall_target else "F1 max"
    target_ok = "✓ ≥0.80" if f1 >= 0.80 else "✗ <0.80"

    print(f"  {name:<12} F1={f1:.4f} {target_ok}  "
          f"Recall={recall:.4f}  Precision={precision:.4f}  "
          f"AUC={auc:.4f}  thr={threshold:.3f} ({thr_label})")

    return {
        "f1": round(f1, 4), "recall": round(recall, 4),
        "precision": round(precision, 4), "auc": round(auc, 4),
        "aupr": round(aupr, 4), "threshold": round(threshold, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODEL EĞİTİM FONKSİYONLARI
# ─────────────────────────────────────────────────────────────────────────────

def train_lgbm(X_train, y_train, X_test, y_test,
               feature_cols, recall_target=None):
    if not LGB_AVAILABLE:
        return None, {}

    neg, pos = safe_bincount(y_train)
    if pos == 0:
        print("  UYARI: Train setinde pozitif örnek yok, LightGBM atlanıyor.")
        return None, {}

    scale_pos = neg / pos
    params    = {**LGBM_PARAMS, "scale_pos_weight": scale_pos}

    t0        = time.time()
    dtrain    = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    dval      = lgb.Dataset(X_test,  label=y_test,  feature_name=feature_cols,
                            reference=dtrain)
    callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)]
    model     = lgb.train(params, dtrain, num_boost_round=500,
                          valid_sets=[dval], callbacks=callbacks)
    elapsed   = time.time() - t0

    y_prob    = model.predict(X_test)
    threshold = select_threshold(y_test, y_prob, recall_target)
    metrics   = print_metrics("LightGBM", y_test, y_prob, threshold, recall_target)
    metrics["time"] = round(elapsed, 1)
    return model, metrics


def train_rf(X_train, y_train, X_test, y_test, recall_target=None):
    neg, pos = safe_bincount(y_train)
    if pos == 0:
        print("  UYARI: Train setinde pozitif örnek yok, RF atlanıyor.")
        return None, {}

    t0    = time.time()
    model = RandomForestClassifier(
        n_estimators=200, max_depth=12, min_samples_leaf=5,
        class_weight="balanced", n_jobs=-1, random_state=42,
    )
    model.fit(X_train, y_train)
    elapsed = time.time() - t0

    y_prob    = model.predict_proba(X_test)[:, 1]
    threshold = select_threshold(y_test, y_prob, recall_target)
    metrics   = print_metrics("RF", y_test, y_prob, threshold, recall_target)
    metrics["time"] = round(elapsed, 1)
    return model, metrics


def train_xgb(X_train, y_train, X_test, y_test, recall_target=None):
    if not XGB_AVAILABLE:
        return None, {}

    neg, pos = safe_bincount(y_train)
    if pos == 0:
        print("  UYARI: Train setinde pozitif örnek yok, XGBoost atlanıyor.")
        return None, {}

    scale_pos = neg / max(pos, 1)
    t0        = time.time()
    model     = XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=scale_pos, eval_metric="logloss",
        random_state=42, verbosity=0,
    )
    model.fit(X_train, y_train)
    elapsed = time.time() - t0

    y_prob    = model.predict_proba(X_test)[:, 1]
    threshold = select_threshold(y_test, y_prob, recall_target)
    metrics   = print_metrics("XGBoost", y_test, y_prob, threshold, recall_target)
    metrics["time"] = round(elapsed, 1)
    return model, metrics


# ─────────────────────────────────────────────────────────────────────────────
# GÖRSELLEŞTİRME
# ─────────────────────────────────────────────────────────────────────────────

def _plot_all(disease, out_dir, feature_cols,
              X_test, y_test,
              lgb_model, rf_model, xgb_model,
              results, shap_df):
    """ROC-AUC, PR eğrisi ve SHAP bar grafiği üretir."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import roc_curve, precision_recall_curve
    except ImportError:
        print("  matplotlib bulunamadı, görselleştirme atlandı.")
        return

    plots_dir = os.path.join(out_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    colors = {"LightGBM": "#2196F3", "RF": "#4CAF50", "XGBoost": "#FF9800"}
    models = []
    if lgb_model:  models.append(("LightGBM", lgb_model, "lgb"))
    if rf_model:   models.append(("RF",        rf_model,  "rf"))
    if xgb_model:  models.append(("XGBoost",   xgb_model, "xgb"))

    def get_prob(name, model):
        if name == "LightGBM":
            return model.predict(X_test)
        return model.predict_proba(X_test)[:, 1]

    # ROC-AUC
    fig, ax = plt.subplots(figsize=(7, 6))
    for name, model, key in models:
        try:
            y_prob      = get_prob(name, model)
            fpr, tpr, _ = roc_curve(y_test, y_prob)
            auc_val     = results.get(key, {}).get("auc", 0)
            ax.plot(fpr, tpr, label=f"{name} (AUC={auc_val:.4f})",
                    color=colors[name], linewidth=2)
        except Exception:
            pass
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4, linewidth=1)
    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate",  fontsize=12)
    ax.set_title(f"ROC-AUC Eğrisi — {disease.upper()}", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(plots_dir, f"roc_{disease}.png"), dpi=150)
    plt.close(fig)

    # Precision-Recall
    fig, ax = plt.subplots(figsize=(7, 6))
    for name, model, key in models:
        try:
            y_prob       = get_prob(name, model)
            prec, rec, _ = precision_recall_curve(y_test, y_prob)
            aupr_val     = results.get(key, {}).get("aupr", 0)
            ax.plot(rec, prec, label=f"{name} (PR-AUC={aupr_val:.4f})",
                    color=colors[name], linewidth=2)
        except Exception:
            pass
    baseline = y_test.mean()
    ax.axhline(baseline, color="gray", linestyle="--", alpha=0.5,
               label=f"Baseline ({baseline:.3f})")
    ax.set_xlabel("Recall",    fontsize=12)
    ax.set_ylabel("Precision", fontsize=12)
    ax.set_title(f"Precision-Recall Eğrisi — {disease.upper()}", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(plots_dir, f"pr_{disease}.png"), dpi=150)
    plt.close(fig)

    # SHAP
    if shap_df is not None and not shap_df.empty:
        top10   = shap_df.head(10)
        fig, ax = plt.subplots(figsize=(8, 5))
        bars    = ax.barh(top10["feature"][::-1], top10["mean_shap"][::-1],
                          color="#2196F3", alpha=0.85)
        ax.set_xlabel("Ortalama |SHAP Değeri|", fontsize=12)
        ax.set_title(f"SHAP Feature Importance — {disease.upper()}", fontsize=14, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        for bar, val in zip(bars, top10["mean_shap"][::-1]):
            ax.text(bar.get_width() + 0.001, bar.get_y() + bar.get_height() / 2,
                    f"{val:.3f}", va="center", fontsize=9)
        fig.tight_layout()
        fig.savefig(os.path.join(plots_dir, f"shap_{disease}.png"), dpi=150)
        plt.close(fig)

    print(f"  Grafikler: {plots_dir}/")


# ─────────────────────────────────────────────────────────────────────────────
# ANA EĞİTİM FONKSİYONU
# ─────────────────────────────────────────────────────────────────────────────

def train_disease(disease: str, data_dir: str, out_dir: str,
                  feature_cols: list, label: str = "") -> dict:
    print(f"\n{'='*55}")
    print(f"  {disease.upper()} MODELİ{' — ' + label if label else ''}")
    print(f"{'='*55}")

    path = os.path.join(data_dir, f"features_{disease}.csv")
    df   = pd.read_csv(path)

    if disease == "cardiac":
        cardiac_cols = [
            "hr_mean", "hr_std", "hr_min", "hr_max", "hr_last", "hr_slope", "hr_hrv",
            "ecg_rr_mean_ms", "ecg_rr_std_ms", "ecg_rmssd_ms", "ecg_pnn50",
            "ecg_amp_mean", "ecg_amp_std", "ecg_amp_min", "ecg_amp_slope",
            "ga_weeks", "pna_days", "pma_weeks",
        ]
        feature_cols = [c for c in cardiac_cols if c in df.columns]
    else:
        feature_cols = [c for c in feature_cols if c in df.columns]

    # NaN → 0 (eksik ECG gibi durumlar)
    X      = np.nan_to_num(df[feature_cols].values, nan=0.0)
    y      = df["label"].values
    groups = df["patient_id"].values

    train_mask, test_mask = ga_stratified_split(df, groups)

    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]

    train_patients = set(groups[train_mask])
    test_patients  = set(groups[test_mask])
    neg_c, pos_c   = safe_bincount(y_train)

    print(f"  Train: {len(train_patients)} hasta, {len(X_train):,} pencere")
    print(f"  Test:  {len(test_patients)} hasta,  {len(X_test):,} pencere")
    print(f"  Sınıf dengesi — neg:{neg_c}, pos:{pos_c}, "
          f"scale_pos_weight={neg_c/max(pos_c,1):.1f}")

    if pos_c == 0:
        print("  HATA: Train setinde hiç pozitif örnek yok. Daha fazla hasta verisi gerekli.")
        return {}

    recall_target = RECALL_TARGETS.get(disease)

    print(f"\n  {'─'*45}")
    print(f"  Model Karşılaştırması")
    print(f"  {'─'*45}")

    lgb_model, lgb_metrics = train_lgbm(
        X_train, y_train, X_test, y_test, feature_cols, recall_target
    )
    rf_model,  rf_metrics  = train_rf(
        X_train, y_train, X_test, y_test, recall_target
    )
    xgb_model, xgb_metrics = train_xgb(
        X_train, y_train, X_test, y_test, recall_target
    )

    # Kazanan modeli belirle
    results = {}
    if lgb_metrics: results["lgb"] = lgb_metrics
    if rf_metrics:  results["rf"]  = rf_metrics
    if xgb_metrics: results["xgb"] = xgb_metrics

    if not results:
        print("  HATA: Hiçbir model eğitilemedi.")
        return {}

    # Apnea: recall öncelikli; Cardiac/Sepsis: F1 öncelikli
    if disease == "apnea":
        best_name = max(results, key=lambda k: (
            results[k].get("recall", 0),
            results[k].get("precision", 0),
        ))
    else:
        best_name = max(results, key=lambda k: (
            results[k].get("f1", 0),
            results[k].get("recall", 0),
        ))

    model_map  = {"lgb": lgb_model, "rf": rf_model, "xgb": xgb_model}
    best_model = model_map[best_name]

    print(f"\n  → Kazanan: {best_name.upper()} "
          f"(F1={results[best_name]['f1']:.4f})")

    # Sınıflandırma raporu
    best_thr = results[best_name]["threshold"]
    if best_name == "lgb":
        y_prob_best = lgb_model.predict(X_test)
    elif best_name == "rf":
        y_prob_best = rf_model.predict_proba(X_test)[:, 1]
    else:
        y_prob_best = xgb_model.predict_proba(X_test)[:, 1]

    y_pred_best = (y_prob_best >= best_thr).astype(int)
    print(f"\n  Sınıflandırma Raporu ({best_name.upper()}):")
    print(classification_report(y_test, y_pred_best,
                                target_names=["negatif", "pozitif"], labels=[0, 1]))
    cm = confusion_matrix(y_test, y_pred_best, labels=[0, 1])
    print(f"  Confusion matrix:\n  {cm}")

    # SHAP
    print(f"\n  SHAP ({best_name.upper()}) hesaplanıyor...")
    shap_df = pd.DataFrame()
    try:
        explainer = shap.TreeExplainer(best_model)
        sv        = explainer.shap_values(X_test[:500])

        if isinstance(sv, list):
            sv = np.array(sv[1])
        elif isinstance(sv, np.ndarray) and sv.ndim == 3:
            sv = sv[:, :, 1]

        shap_df = pd.DataFrame({
            "feature":   feature_cols,
            "mean_shap": np.abs(sv).mean(axis=0),
        }).sort_values("mean_shap", ascending=False)

        print("\n  Top 10 özellik:")
        print(shap_df.head(10).to_string(index=False))

        shap_df.to_csv(os.path.join(out_dir, f"shap_{disease}.csv"), index=False)
    except Exception as e:
        print(f"  SHAP hata: {e}")

    # Kaydet
    os.makedirs(out_dir, exist_ok=True)

    for name, model in [("lgb", lgb_model), ("rf", rf_model), ("xgb", xgb_model)]:
        if model is not None:
            with open(os.path.join(out_dir, f"model_{name}_{disease}.pkl"), "wb") as f:
                pickle.dump(model, f)

    # Kazanan modeli ayrıca kaydet (inference için)
    with open(os.path.join(out_dir, f"model_{disease}.pkl"), "wb") as f:
        pickle.dump(best_model, f)

    metrics_out = {
        "disease":        disease,
        "best_model":     best_name,
        "recall_target":  recall_target,
        "results":        results,
        "feature_cols":   feature_cols,
        "n_train":        int(len(X_train)),
        "n_test":         int(len(X_test)),
        "pos_ratio":      round(float(y_test.mean()), 4),
        "roc_auc":        results[best_name].get("auc"),
        "pr_auc":         results[best_name].get("aupr"),
        "best_threshold": results[best_name].get("threshold"),
    }
    if lgb_model and hasattr(lgb_model, "best_iteration"):
        metrics_out["best_iter"] = lgb_model.best_iteration

    with open(os.path.join(out_dir, f"metrics_{disease}.json"), "w") as f:
        json.dump(metrics_out, f, indent=2)

    _plot_all(disease, out_dir, feature_cols,
              X_test, y_test,
              lgb_model, rf_model, xgb_model if XGB_AVAILABLE else None,
              results, shap_df if not shap_df.empty else None)

    print(f"\n  Kaydedildi: {out_dir}/")
    return metrics_out


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def cross_validate_disease(disease: str, data_dir: str, out_dir: str,
                           feature_cols: list, n_folds: int = 5) -> dict:
    print(f"\n{'='*55}")
    print(f"  {disease.upper()} — {n_folds}-Fold Hasta-Bazlı CV")
    print(f"{'='*55}")

    if not LGB_AVAILABLE:
        print("  LightGBM gerekli. pip install lightgbm")
        return {}

    path         = os.path.join(data_dir, f"features_{disease}.csv")
    df           = pd.read_csv(path)
    feature_cols = [c for c in feature_cols if c in df.columns]

    X      = np.nan_to_num(df[feature_cols].values, nan=0.0)
    y      = df["label"].values
    groups = df["patient_id"].values

    gkf           = GroupKFold(n_splits=n_folds)
    fold_metrics  = []
    recall_target = RECALL_TARGETS.get(disease)

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups), 1):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        train_pids = set(groups[train_idx])
        test_pids  = set(groups[test_idx])

        if len(np.unique(y_te)) < 2:
            print(f"  Fold {fold}: test setinde tek sınıf, atlanıyor.")
            continue

        neg, pos  = safe_bincount(y_tr)
        if pos == 0:
            print(f"  Fold {fold}: pozitif örnek yok, atlanıyor.")
            continue

        scale_pos = neg / pos
        params    = {**LGBM_PARAMS, "scale_pos_weight": scale_pos}

        dtrain    = lgb.Dataset(X_tr, label=y_tr, feature_name=feature_cols)
        dval      = lgb.Dataset(X_te, label=y_te, feature_name=feature_cols,
                               reference=dtrain)
        callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)]
        model     = lgb.train(params, dtrain, num_boost_round=500,
                             valid_sets=[dval], callbacks=callbacks)

        y_prob   = model.predict(X_te)
        auc      = roc_auc_score(y_te, y_prob)
        aupr     = average_precision_score(y_te, y_prob)
        best_thr = select_threshold(y_te, y_prob, recall_target)
        f1       = float(f1_score(y_te, (y_prob >= best_thr).astype(int)))

        fold_metrics.append({
            "fold":              fold,
            "n_train_patients":  len(train_pids),
            "n_test_patients":   len(test_pids),
            "n_train":           len(X_tr),
            "n_test":            len(X_te),
            "roc_auc":           round(auc,  4),
            "pr_auc":            round(aupr, 4),
            "f1":                round(f1,   4),
            "best_iter":         model.best_iteration,
        })

        print(f"  Fold {fold}  |  {len(train_pids)} hasta train / "
              f"{len(test_pids)} test  |  "
              f"ROC-AUC={auc:.4f}  PR-AUC={aupr:.4f}  F1={f1:.4f}")

    if not fold_metrics:
        print("  CV tamamlanamadı.")
        return {}

    aucs  = [m["roc_auc"] for m in fold_metrics]
    auprs = [m["pr_auc"]  for m in fold_metrics]
    f1s   = [m["f1"]      for m in fold_metrics]

    print(f"\n  ── Ortalama ({n_folds} fold) ──────────────────────────")
    print(f"  ROC-AUC : {np.mean(aucs):.4f}  ± {np.std(aucs):.4f}")
    print(f"  PR-AUC  : {np.mean(auprs):.4f}  ± {np.std(auprs):.4f}")
    print(f"  F1      : {np.mean(f1s):.4f}  ± {np.std(f1s):.4f}")

    cv_result = {
        "disease":      disease,
        "n_folds":      n_folds,
        "folds":        fold_metrics,
        "mean_roc_auc": round(float(np.mean(aucs)),  4),
        "std_roc_auc":  round(float(np.std(aucs)),   4),
        "mean_pr_auc":  round(float(np.mean(auprs)), 4),
        "std_pr_auc":   round(float(np.std(auprs)),  4),
        "mean_f1":      round(float(np.mean(f1s)),   4),
        "std_f1":       round(float(np.std(f1s)),    4),
    }

    os.makedirs(out_dir, exist_ok=True)
    cv_path = os.path.join(out_dir, f"cv_{disease}.json")
    with open(cv_path, "w") as f:
        json.dump(cv_result, f, indent=2)
    print(f"\n  Kaydedildi: {cv_path}")
    return cv_result


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Manifetch NICU — Model eğitimi"
    )
    parser.add_argument("--data_dir", default="data/all_data")
    parser.add_argument("--out_dir",  default="models")
    parser.add_argument("--disease",  default="all",
                        choices=["all"] + DISEASES)
    parser.add_argument("--cv",       action="store_true",
                        help="5-fold cross-validation çalıştır (final eğitimden önce)")
    parser.add_argument("--cv_only",  action="store_true",
                        help="Sadece CV — final model eğitme")
    args    = parser.parse_args()
    targets = DISEASES if args.disease == "all" else [args.disease]

    print("=" * 55)
    print("Manifetch NICU — Model Eğitimi")
    algos = "RF"
    if XGB_AVAILABLE: algos += " + XGBoost"
    if LGB_AVAILABLE: algos += " + LightGBM"
    print(f"Algoritmalar: {algos}")
    print("=" * 55)

    # Cross-validation
    if args.cv or args.cv_only:
        cv_summary = []
        for disease in targets:
            r = cross_validate_disease(disease, args.data_dir, args.out_dir,
                                       FEATURE_COLS_ALL)
            if r:
                cv_summary.append(r)

        print(f"\n{'='*55}")
        print("  CV ÖZET")
        print(f"{'='*55}")
        for r in cv_summary:
            print(f"  {r['disease']:<10}  "
                  f"ROC-AUC={r['mean_roc_auc']:.4f}±{r['std_roc_auc']:.4f}  "
                  f"PR-AUC={r['mean_pr_auc']:.4f}±{r['std_pr_auc']:.4f}  "
                  f"F1={r['mean_f1']:.4f}±{r['std_f1']:.4f}")

        # DÜZELTME: --cv_only mantığı netleştirildi
        if args.cv_only:
            print("\n--cv_only: Final model eğitimi atlandı.")
            return

    # Final model eğitimi
    all_metrics = []
    for disease in targets:
        m = train_disease(disease, args.data_dir, args.out_dir, FEATURE_COLS_ALL)
        if m:
            all_metrics.append(m)

    if not all_metrics:
        print("\nHiçbir model eğitilemedi.")
        return

    print(f"\n{'='*75}")
    print("  ÖZET")
    print(f"{'='*75}")
    print(f"  {'Hastalık':<12} {'RF F1':>8} {'XGB F1':>8} {'LGB F1':>8} "
          f"{'RF Rec':>8} {'XGB Rec':>8} {'LGB Rec':>8} {'Kazanan':>10}")
    print(f"  {'─'*75}")
    for m in all_metrics:
        r       = m.get("results", {})
        rf_f1   = f"{r['rf']['f1']:.4f}"      if "rf"  in r else "   -    "
        xgb_f1  = f"{r['xgb']['f1']:.4f}"     if "xgb" in r else "   -    "
        lgb_f1  = f"{r['lgb']['f1']:.4f}"     if "lgb" in r else "   -    "
        rf_rec  = f"{r['rf']['recall']:.4f}"   if "rf"  in r else "   -    "
        xgb_rec = f"{r['xgb']['recall']:.4f}"  if "xgb" in r else "   -    "
        lgb_rec = f"{r['lgb']['recall']:.4f}"  if "lgb" in r else "   -    "
        print(f"  {m['disease']:<12} {rf_f1:>8} {xgb_f1:>8} {lgb_f1:>8} "
              f"{rf_rec:>8} {xgb_rec:>8} {lgb_rec:>8} "
              f"{m['best_model'].upper():>10}")


if __name__ == "__main__":
    main()