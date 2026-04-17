import sys, os, uuid, random, pickle, unittest, json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_module.inference_service import (
    InferenceService, VitalMeasurement, AIResult,
    VITAL_FEATURE_COLS, ECG_FEATURE_COLS, MODEL_TYPES,
    LGB_AVAILABLE,
)

F1_TARGET = 0.80   # TC-36


def make_measurements(patient_id, scenario="healthy", n=30,
                       ga=35, pna=14, pma=37.0):
    random.seed(42)
    measurements = []
    for s in range(n):
        if scenario == "sepsis":
            hr_val   = 185 + random.gauss(0, 5)
            spo2_val = 86  + random.gauss(0, 1)
            rr_val   = 65  + random.gauss(0, 3)
        elif scenario == "apnea":
            hr_val   = 130 + random.gauss(0, 5)
            spo2_val = 82  + random.gauss(0, 1)
            rr_val   = max(0, 5 * random.random())
        elif scenario == "cardiac":
            hr_val   = 220 + 60 * abs(random.gauss(0, 1))
            spo2_val = 93  + random.gauss(0, 1)
            rr_val   = 45  + random.gauss(0, 3)
        else:
            hr_val   = 145 + random.gauss(0, 5)
            spo2_val = 96  + random.gauss(0, 1)
            rr_val   = 45  + random.gauss(0, 3)

        measurements.append(VitalMeasurement(patient_id, float(s), "HEART_RATE", hr_val, ga, pna, pma))
        measurements.append(VitalMeasurement(patient_id, float(s), "SPO2", spo2_val, ga, pna, pma))
        if s % 2 == 0:
            measurements.append(VitalMeasurement(patient_id, float(s), "RESP_RATE", rr_val, ga, pna, pma))
    return measurements


def _predict_with_model(model, vector: np.ndarray) -> float:
    """Model tipine göre doğru predict metodunu çağırır."""
    if LGB_AVAILABLE and hasattr(model, "predict") and not hasattr(model, "predict_proba"):
        return float(model.predict(vector)[0])
    return float(model.predict_proba(vector)[0][1])


class TestAIModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.service   = InferenceService()
        cls.model_dir = cls.service.model_dir

    # ── TC-14: RF, XGBoost, LightGBM dosyaları mevcut ve skor üretiyor ──────

    def test_tc14_rf_xgb_both_loaded(self):
        """TC-14: RF ve XGBoost model dosyaları diskte mevcut olmalı."""
        for condition in ["sepsis", "apnea", "cardiac"]:
            rf_path  = os.path.join(self.model_dir, f"model_rf_{condition}.pkl")
            xgb_path = os.path.join(self.model_dir, f"model_xgb_{condition}.pkl")
            self.assertTrue(os.path.exists(rf_path),  f"RF model eksik: {rf_path}")
            self.assertTrue(os.path.exists(xgb_path), f"XGB model eksik: {xgb_path}")
        print("TC-14 ✓ RF ve XGBoost model dosyaları mevcut")

    def test_tc14_rf_xgb_produce_scores(self):
        """
        TC-14: RF, XGBoost ve LightGBM modelleri 0-1 arasında risk skoru üretiyor.

        DÜZELTME: Her model tipi _models dict'inden doğrudan çekilip ayrı ayrı
        çalıştırılıyor. Eski halde runner.predict her iterasyonda best_model'i
        seçtiğinden RF/XGB/LGB gerçekte test edilmiyordu.
        """
        pid  = str(uuid.uuid4())
        meas = make_measurements(pid, "sepsis")

        for condition in ["sepsis", "apnea", "cardiac"]:
            feats        = self.service.preprocess(meas, condition)
            feature_cols = self.service._get_feature_cols(condition)
            threshold    = self.service._get_threshold(condition)

            vector = np.array(
                [feats.get(c, 0.0) for c in feature_cols],
                dtype=float,
            ).reshape(1, -1)
            vector = np.nan_to_num(vector, nan=0.0)

            tested = []
            for mtype in MODEL_TYPES:
                model_key = f"{condition}_{mtype}"
                model = self.service._models.get(model_key)
                if model is None:
                    continue

                prob  = _predict_with_model(model, vector)
                label = int(prob >= threshold)

                self.assertGreaterEqual(prob, 0.0,
                    f"{condition}/{mtype}: skor 0'dan küçük")
                self.assertLessEqual(prob, 1.0,
                    f"{condition}/{mtype}: skor 1'den büyük")
                self.assertIn(label, [0, 1],
                    f"{condition}/{mtype}: label 0 veya 1 olmalı")
                tested.append(mtype)

            self.assertGreater(
                len(tested), 0,
                f"{condition} için hiç model yüklenmemiş"
            )
            print(f"TC-14 ✓ {condition}: {tested} → skorlar üretildi")

    # ── TC-11: SHAP top-3 özellikler ────────────────────────────────────────

    def test_tc11_shap_top3_exists(self):
        """TC-11: SHAP top-3 özellikler hesaplanmalı."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(pid, make_measurements(pid, "sepsis"))
        self.assertIsInstance(result.shap_top3, dict)
        for condition in ["sepsis", "apnea", "cardiac"]:
            self.assertIn(condition, result.shap_top3)
            top3 = result.shap_top3[condition]
            self.assertGreaterEqual(len(top3), 1)
            for item in top3:
                self.assertIn("feature",    item)
                self.assertIn("importance", item)
        print(f"TC-11 ✓ SHAP top-3: {[x['feature'] for x in result.shap_top3['sepsis']]}")

    # ── TC-16: runInference AIResult döndürmeli ───────────────────────────────

    def test_tc16_inference_returns_airesult(self):
        """TC-16: runInference AIResult döndürmeli."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(pid, make_measurements(pid, "sepsis"))
        self.assertIsInstance(result, AIResult)
        self.assertEqual(result.patientId, pid)
        self.assertIn(result.riskLevel, ["LOW", "MEDIUM", "HIGH"])
        self.assertIsInstance(result.sepsis_score,  float)
        self.assertIsInstance(result.apnea_score,   float)
        self.assertIsInstance(result.cardiac_score, float)
        self.assertIn(result.sepsis_label,  [0, 1])
        self.assertIn(result.apnea_label,   [0, 1])
        self.assertIn(result.cardiac_label, [0, 1])
        print(f"TC-16 ✓ AIResult döndü: {result.getFormattedResult()}")

    def test_tc16_sepsis_detected(self):
        """TC-16: Sepsis senaryosunda yüksek risk skoru çıkmalı."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(
            pid, make_measurements(pid, "sepsis", ga=28, pna=10, pma=29.4)
        )
        self.assertGreater(
            result.sepsis_score, 0.5,
            f"Sepsis skoru çok düşük: {result.sepsis_score}"
        )
        print(f"TC-16 ✓ Sepsis algılandı: score={result.sepsis_score:.4f}")

    def test_tc16_healthy_low_risk(self):
        """TC-16: Sağlıklı senaryoda düşük sepsis skoru çıkmalı."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(
            pid, make_measurements(pid, "healthy", ga=35, pna=14, pma=37.0)
        )
        self.assertLess(
            result.sepsis_score, 0.5,
            f"Sağlıklı hasta sepsis skoru yüksek: {result.sepsis_score}"
        )
        print(f"TC-16 ✓ Sağlıklı hasta: sepsis={result.sepsis_score:.4f}")

    def test_tc16_preprocess_returns_all_features(self):
        """TC-16: preprocess tüm feature'ları döndürmeli."""
        pid   = str(uuid.uuid4())
        feats = self.service.preprocess(make_measurements(pid, "healthy"), "sepsis")
        all_cols = VITAL_FEATURE_COLS + ECG_FEATURE_COLS
        for col in all_cols:
            self.assertIn(col, feats, f"Eksik feature: {col}")
        print(f"TC-16 ✓ preprocess {len(feats)} feature döndürdü")

    def test_tc16_formatted_result(self):
        """TC-16: getFormattedResult string döndürmeli."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(pid, make_measurements(pid, "sepsis"))
        fmt    = result.getFormattedResult()
        self.assertIsInstance(fmt, str)
        self.assertIn(result.riskLevel, fmt)
        print(f"TC-16 ✓ Formatted: {fmt}")

    # ── TC-36: F1 ≥ 0.80 hedefi ─────────────────────────────────────────────

    def test_tc36_f1_target(self):
        """
        TC-36: Model performans hedefleri:
          - Apnea:   Recall ≥ 0.85 (FN maliyeti yüksek — klinik öncelik)
          - Cardiac: F1 ≥ 0.80
          - Sepsis:  F1 ≥ 0.80
        Temporal validation sonuçlarını okur (test_temporal.py çıktısı).
        """
        out_dir    = self.model_dir
        all_passed = True
        missing    = []

        targets = {
            "apnea":   {"metric": "recall", "threshold": 0.85},
            "cardiac": {"metric": "f1",     "threshold": F1_TARGET},
            "sepsis":  {"metric": "f1",     "threshold": F1_TARGET},
        }

        for disease, target in targets.items():
            result_path = os.path.join(out_dir, f"temporal_validation_{disease}.json")

            if not os.path.exists(result_path):
                missing.append(disease)
                continue

            with open(result_path) as f:
                data = json.load(f)

            results        = data.get("results", {})
            metric_key     = target["metric"]
            threshold      = target["threshold"]
            disease_passed = False

            for model_type, metrics in results.items():
                val = metrics.get(metric_key, 0)
                if val >= threshold:
                    print(f"  TC-36 ✓ {disease}/{model_type}: "
                          f"{metric_key.upper()}={val:.4f} ≥ {threshold}")
                    disease_passed = True
                else:
                    print(f"  TC-36 ✗ {disease}/{model_type}: "
                          f"{metric_key.upper()}={val:.4f} < {threshold}")

            if not disease_passed:
                all_passed = False

        if missing:
            self.skipTest(
                f"Temporal validation sonuçları eksik: {missing}. "
                "test_temporal.py çalıştırın."
            )

        self.assertTrue(
            all_passed,
            "Bazı hastalıklar için hiçbir model hedefi karşılamadı."
        )
        print(f"\nTC-36 ✓ Tüm modeller hedefi karşıladı.")

    # ── ModelRunner testi ─────────────────────────────────────────────────────

    def test_model_runner_version(self):
        """ModelRunner.get_model_version() crash yapmadan çalışmalı."""
        version = self.service.runner.get_model_version()
        self.assertIsInstance(version, str)
        self.assertGreater(len(version), 0)
        print(f"ModelRunner ✓ version: {version}")


if __name__ == "__main__":
    print("=" * 60)
    print("Manifetch AI Modül Testi")
    print("=" * 60)
    unittest.main(verbosity=2)