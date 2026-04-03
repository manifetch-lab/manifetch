"""
Manifetch NICU — Inference Service
====================================
LLD: InferenceService sınıfı
nicu_train.py çıktısıyla uyumlu — her hastalık için ayrı model ve pencere.

Methods:
  runInference(patientId, input: List[VitalMeasurement]) -> AIResult
  preprocess(input: List[VitalMeasurement], disease: str) -> FeatureVector
"""

import os
import uuid
import time
import pickle
import json
import threading
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional
from scipy.signal import find_peaks

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

DISEASE_CONFIGS = {
    "sepsis":  {"window_sec": 3600},
    "apnea":   {"window_sec": 600},
    "cardiac": {"window_sec": 1800},
}

VITAL_FEATURE_COLS = [
    "hr_mean", "hr_std", "hr_min", "hr_max", "hr_last", "hr_slope", "hr_hrv",
    "spo2_mean", "spo2_std", "spo2_min", "spo2_max", "spo2_last", "spo2_slope",
    "spo2_pct_below_90", "spo2_min_diff",
    "rr_mean", "rr_std", "rr_min", "rr_max", "rr_last", "rr_slope",
    "rr_pct_below_30", "rr_pct_below_10", "rr_cv", "hr_rr_ratio",
    "ga_weeks", "pna_days", "pma_weeks",
]

ECG_FEATURE_COLS = [
    "ecg_rr_mean_ms", "ecg_rr_std_ms", "ecg_rmssd_ms", "ecg_pnn50",
    "ecg_amp_mean", "ecg_amp_std", "ecg_amp_min", "ecg_amp_slope",
]

ECG_HZ = 25


class VitalMeasurement:
    def __init__(self, patientId, timestamp_sec, signalType, value,
                 gestationalAgeWeeks=30, postnatalAgeDays=14, pma_weeks=32.0):
        self.patientId           = patientId
        self.timestamp_sec       = timestamp_sec
        self.signalType          = signalType
        self.value               = value
        self.gestationalAgeWeeks = gestationalAgeWeeks
        self.postnatalAgeDays    = postnatalAgeDays
        self.pma_weeks           = pma_weeks


class AIResult:
    def __init__(self, resultId, patientId, timeStamp,
                 sepsis_score, apnea_score, cardiac_score,
                 sepsis_label, apnea_label, cardiac_label, shap_top3=None):
        self.resultId      = resultId
        self.patientId     = patientId
        self.timeStamp     = timeStamp
        self.sepsis_score  = sepsis_score
        self.apnea_score   = apnea_score
        self.cardiac_score = cardiac_score
        self.sepsis_label  = sepsis_label
        self.apnea_label   = apnea_label
        self.cardiac_label = cardiac_label
        self.shap_top3     = shap_top3 or {}
        self.riskScore = round(max(sepsis_score, apnea_score, cardiac_score), 4)
        if self.riskScore >= 0.75:   self.riskLevel = "HIGH"
        elif self.riskScore >= 0.50: self.riskLevel = "MEDIUM"
        else:                        self.riskLevel = "LOW"

    def getFormattedResult(self):
        active = []
        if self.sepsis_label:  active.append(f"Sepsis({self.sepsis_score:.2f})")
        if self.apnea_label:   active.append(f"Apnea({self.apnea_score:.2f})")
        if self.cardiac_label: active.append(f"Cardiac({self.cardiac_score:.2f})")
        conditions = ", ".join(active) if active else "Normal"
        return (f"[{self.riskLevel}] {conditions} | "
                f"RiskScore={self.riskScore} | PatientId={self.patientId[:8]}")

    def to_dict(self):
        return {
            "resultId": self.resultId, "patientId": self.patientId,
            "timeStamp": self.timeStamp.isoformat(),
            "riskScore": self.riskScore, "riskLevel": self.riskLevel,
            "sepsis_score": self.sepsis_score, "apnea_score": self.apnea_score,
            "cardiac_score": self.cardiac_score,
            "sepsis_label": self.sepsis_label, "apnea_label": self.apnea_label,
            "cardiac_label": self.cardiac_label, "shap_top3": self.shap_top3,
        }


def extract_ecg_beat_features(ecg_vals, fs=ECG_HZ):
    default = {k: 0.0 for k in ECG_FEATURE_COLS}
    if len(ecg_vals) < fs * 5:
        return default
    height_thr = np.percentile(ecg_vals, 80)
    min_dist   = max(3, int(fs * 60 / 300))
    peaks, _   = find_peaks(ecg_vals, height=height_thr, distance=min_dist)
    if len(peaks) < 5:
        return default
    rr_ms  = np.diff(peaks) / fs * 1000.0
    amps   = ecg_vals[peaks[1:]]
    rr_diff = np.abs(np.diff(rr_ms))
    rmssd   = float(np.sqrt(np.mean(rr_diff**2))) if len(rr_diff) > 0 else 0.0
    pnn50   = float(np.mean(rr_diff > 50)) if len(rr_diff) > 0 else 0.0
    slope   = float(np.polyfit(np.arange(len(amps)), amps, 1)[0]) if len(amps) > 1 else 0.0
    return {
        "ecg_rr_mean_ms": float(np.mean(rr_ms)), "ecg_rr_std_ms": float(np.std(rr_ms)),
        "ecg_rmssd_ms": rmssd, "ecg_pnn50": pnn50,
        "ecg_amp_mean": float(np.mean(amps)), "ecg_amp_std": float(np.std(amps)),
        "ecg_amp_min": float(np.min(amps)), "ecg_amp_slope": slope,
    }


class InferenceService:
    def __init__(self, model_dir=DEFAULT_MODEL_DIR):
        self.model_dir = model_dir
        self._models   = {}
        self._meta     = {}
        self._shap_explainers = {}
        self._shap_lock = threading.Lock()  # SHAP thread-safe değil
        self._load_models()

    def _load_models(self):
        for disease in DISEASE_CONFIGS:
            for prefix in [f"model_{disease}", f"model_lgb_{disease}",
               f"model_xgb_{disease}", f"model_rf_{disease}",
               f"{disease}_best"]:
                path = os.path.join(self.model_dir, f"{prefix}.pkl")
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        self._models[disease] = pickle.load(f)
                    print(f"[InferenceService] {disease} → {prefix}.pkl")
                    break
            meta_path = os.path.join(self.model_dir, f"metrics_{disease}.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    self._meta[disease] = json.load(f)
        if not self._models:
            raise FileNotFoundError(f"Model bulunamadı: {self.model_dir}")
        if SHAP_AVAILABLE:
            for disease, model in self._models.items():
                try:
                    self._shap_explainers[disease] = shap.TreeExplainer(model)
                except Exception:
                    pass
        print(f"[InferenceService] {len(self._models)} model yüklendi")

    def _get_feature_cols(self, disease):
        if disease in self._meta:
            return self._meta[disease].get("feature_cols",
                                           VITAL_FEATURE_COLS + ECG_FEATURE_COLS)
        return VITAL_FEATURE_COLS + ECG_FEATURE_COLS

    def _get_threshold(self, disease):
        if disease in self._meta:
            results = self._meta[disease].get("results", {})
            best    = self._meta[disease].get("best_model", "xgb")
            return results.get(best, {}).get("threshold", 0.5)
        return 0.5

    def preprocess(self, measurements, disease="sepsis"):
        if not measurements:
            raise ValueError("Ölçüm listesi boş.")
        hr_vals   = [m.value for m in measurements if m.signalType == "HEART_RATE"]
        spo2_vals = [m.value for m in measurements if m.signalType == "SPO2"]
        rr_vals   = [m.value for m in measurements if m.signalType == "RESP_RATE"]
        ecg_vals  = [m.value for m in measurements if m.signalType == "ECG"]
        if not hr_vals:
            raise ValueError("HR verisi zorunludur.")
        if not spo2_vals:
            spo2_vals = [95.0] * len(hr_vals)
        if not rr_vals:
            # Disease'e göre farklı RR fallback:
            #   apnea  → RR sıfıra yakın (nefes durması)
            #   sepsis → RR yüksek (takipne)
            #   cardiac → RR normal
            rr_fallback = {"apnea": 5.0, "sepsis": 65.0, "cardiac": 45.0}
            rr_vals = [rr_fallback.get(disease, 45.0)] * len(hr_vals)

        hr   = np.array(hr_vals,   dtype=float)
        spo2 = np.array(spo2_vals, dtype=float)
        rr   = np.array(rr_vals,   dtype=float)
        feats = {}

        for name, arr in [("hr", hr), ("spo2", spo2), ("rr", rr)]:
            clean = arr[~np.isnan(arr)]
            if len(clean) == 0:
                for s in ["mean","std","min","max","last","slope"]:
                    feats[f"{name}_{s}"] = 0.0
                continue
            feats[f"{name}_mean"]  = float(np.mean(clean))
            feats[f"{name}_std"]   = float(np.std(clean))
            feats[f"{name}_min"]   = float(np.min(clean))
            feats[f"{name}_max"]   = float(np.max(clean))
            feats[f"{name}_last"]  = float(clean[-1])
            feats[f"{name}_slope"] = float(np.polyfit(np.arange(len(clean)), clean, 1)[0]) if len(clean) > 1 else 0.0

        spo2_c = spo2[~np.isnan(spo2)]
        feats["spo2_pct_below_90"] = float(np.mean(spo2_c < 90)) if len(spo2_c) > 0 else 0.0
        # Ani SpO2 düşüş hızı
        feats["spo2_min_diff"] = float(np.min(np.diff(spo2_c))) if len(spo2_c) > 1 else 0.0

        hr_c   = hr[~np.isnan(hr)]
        feats["hr_hrv"] = float(np.std(hr_c)) if len(hr_c) > 0 else 0.0

        rr_c   = rr[~np.isnan(rr)]
        feats["rr_pct_below_30"] = float(np.mean(rr_c < 30)) if len(rr_c) > 0 else 0.0
        # Nefes durması oranı
        feats["rr_pct_below_10"] = float(np.mean(rr_c < 10)) if len(rr_c) > 0 else 0.0
        # RR değişkenlik katsayısı
        rr_mean = float(np.mean(rr_c)) if len(rr_c) > 0 else 1.0
        feats["rr_cv"] = float(np.std(rr_c) / max(rr_mean, 1.0)) if len(rr_c) > 0 else 0.0
        # HR/RR oranı
        hr_mean = feats.get("hr_mean", 0.0)
        feats["hr_rr_ratio"] = float(hr_mean / max(rr_mean, 1.0)) if rr_mean > 0 else 0.0
        feats["ga_weeks"]  = float(measurements[0].gestationalAgeWeeks)
        feats["pna_days"]  = float(measurements[0].postnatalAgeDays)
        feats["pma_weeks"] = float(measurements[0].pma_weeks)

        if ecg_vals:
            feats.update(extract_ecg_beat_features(np.array(ecg_vals)))
        else:
            hr_mean   = feats.get("hr_mean", 150)
            rr_est_ms = 60000.0 / max(hr_mean, 30)
            feats.update({
                "ecg_rr_mean_ms": rr_est_ms, "ecg_rr_std_ms": rr_est_ms * 0.05,
                "ecg_rmssd_ms": 20.0, "ecg_pnn50": 0.1,
                "ecg_amp_mean": 0.8, "ecg_amp_std": 0.05,
                "ecg_amp_min": 0.6, "ecg_amp_slope": 0.0,
            })
        return feats

    def _predict_disease(self, features, disease):
        model = self._models.get(disease)
        if model is None:
            return 0.0, 0
        feature_cols = self._get_feature_cols(disease)
        threshold    = self._get_threshold(disease)
        vector = np.array([features.get(c, 0.0) for c in feature_cols],
                          dtype=float).reshape(1, -1)
        if LGB_AVAILABLE and hasattr(model, "predict") and not hasattr(model, "predict_proba"):
            prob = float(model.predict(vector)[0])
        else:
            prob = float(model.predict_proba(vector)[0][1])
        return round(prob, 4), int(prob >= threshold)

    def _compute_shap(self, features, disease, feature_cols):
        if not SHAP_AVAILABLE or disease not in self._shap_explainers:
            return []
        try:
            with self._shap_lock:  # TreeExplainer thread-safe değil
                explainer = self._shap_explainers[disease]
                vector    = np.array([features.get(c, 0.0) for c in feature_cols],
                                     dtype=float).reshape(1, -1)
                sv = explainer.shap_values(vector)
            if isinstance(sv, list): sv = np.array(sv[1])
            elif isinstance(sv, np.ndarray) and sv.ndim == 3: sv = sv[:,:,1]
            mean_abs = np.abs(sv).flatten()
            top3_idx = [int(x) for x in np.argsort(mean_abs)[::-1][:3]]
            return [{"feature": feature_cols[i], "importance": round(float(mean_abs[i]), 4)}
                    for i in top3_idx]
        except Exception:
            return []

    def runInference(self, patientId, measurements):
        t_start   = time.time()
        scores    = {}
        labels    = {}
        shap_top3 = {}

        for disease in DISEASE_CONFIGS:
            feats          = self.preprocess(measurements, disease)
            prob, label    = self._predict_disease(feats, disease)
            scores[disease] = prob
            labels[disease] = label
            feature_cols   = self._get_feature_cols(disease)
            shap_top3[disease] = self._compute_shap(feats, disease, feature_cols)

        result = AIResult(
            resultId      = str(uuid.uuid4()),
            patientId     = patientId,
            timeStamp     = datetime.now(timezone.utc),
            sepsis_score  = scores["sepsis"],
            apnea_score   = scores["apnea"],
            cardiac_score = scores["cardiac"],
            sepsis_label  = labels["sepsis"],
            apnea_label   = labels["apnea"],
            cardiac_label = labels["cardiac"],
            shap_top3     = shap_top3,
        )

        elapsed = round(time.time() - t_start, 3)
        print(f"[InferenceService] {result.getFormattedResult()} | inference={elapsed}s")
        return result


if __name__ == "__main__":
    import random, glob

    print("InferenceService test...\n")
    service = InferenceService()
    pid = str(uuid.uuid4())

    ecg_dir   = os.path.join(os.path.dirname(__file__), "..", "data", "synthetic")
    ecg_files = glob.glob(os.path.join(ecg_dir, "ecg_*.csv"))

    def get_ecg(f, start=100, window=30, fs=25):
        import pandas as pd
        df   = pd.read_csv(f, usecols=["timestamp_sec","ecg_mv"])
        mask = (df["timestamp_sec"] >= start) & (df["timestamp_sec"] < start+window)
        return df[mask]["ecg_mv"].values, df[mask]["timestamp_sec"].values

    def build_meas(pid, hr, spo2, rr, ga, pna, pma, ecg_file=None):
        meas = []
        for s in range(30):
            meas.append(VitalMeasurement(pid, float(s), "HEART_RATE", hr+random.gauss(0,3), ga, pna, pma))
            meas.append(VitalMeasurement(pid, float(s), "SPO2", spo2+random.gauss(0,0.5), ga, pna, pma))
            if s%2==0:
                meas.append(VitalMeasurement(pid, float(s), "RESP_RATE", rr+random.gauss(0,2), ga, pna, pma))
        if ecg_file:
            vals, ts = get_ecg(ecg_file)
            for t, v in zip(ts, vals):
                meas.append(VitalMeasurement(pid, float(t-ts[0]), "ECG", float(v), ga, pna, pma))
        return meas

    ecg_file = ecg_files[0] if ecg_files else None

    print("--- Sepsis ---")
    r = service.runInference(pid, build_meas(pid, 185, 86, 65, 28, 10, 29.4, ecg_file))
    print(f"  {r.sepsis_score=}  {r.apnea_score=}  {r.cardiac_score=}")

    print("\n--- Sağlıklı ---")
    r2 = service.runInference(pid, build_meas(pid, 145, 96, 45, 35, 14, 37.0, ecg_file))
    print(f"  {r2.sepsis_score=}  {r2.apnea_score=}  {r2.cardiac_score=}")