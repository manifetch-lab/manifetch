"""
Manifetch AI Modül Testi
"""
import sys, os, uuid, random, pickle, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inference_service import InferenceService, VitalMeasurement, AIResult, VITAL_FEATURE_COLS, ECG_FEATURE_COLS

def make_measurements(patient_id, scenario="healthy", n=30, ga=35, pna=14, pma=37.0):
    random.seed(42)
    measurements = []
    for s in range(n):
        if scenario == "sepsis":
            hr_val, spo2_val, rr_val = 185+random.gauss(0,5), 86+random.gauss(0,1), 65+random.gauss(0,3)
        elif scenario == "apnea":
            hr_val, spo2_val, rr_val = 130+random.gauss(0,5), 82+random.gauss(0,1), max(0,5*random.random())
        elif scenario == "cardiac":
            hr_val, spo2_val, rr_val = 220+60*abs(random.gauss(0,1)), 93+random.gauss(0,1), 45+random.gauss(0,3)
        else:
            hr_val, spo2_val, rr_val = 145+random.gauss(0,5), 96+random.gauss(0,1), 45+random.gauss(0,3)
        measurements.append(VitalMeasurement(patient_id, float(s), "HEART_RATE", hr_val, ga, pna, pma))
        measurements.append(VitalMeasurement(patient_id, float(s), "SPO2", spo2_val, ga, pna, pma))
        if s % 2 == 0:
            measurements.append(VitalMeasurement(patient_id, float(s), "RESP_RATE", rr_val, ga, pna, pma))
    return measurements

class TestAIModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.service   = InferenceService()
        cls.model_dir = cls.service.model_dir

    def test_tc14_rf_xgb_both_loaded(self):
        """TC-14: RF ve XGBoost modelleri yüklü olmalı."""
        for condition in ["sepsis", "apnea", "cardiac"]:
            rf_path  = os.path.join(self.model_dir, f"model_rf_{condition}.pkl")
            xgb_path = os.path.join(self.model_dir, f"model_xgb_{condition}.pkl")
            self.assertTrue(os.path.exists(rf_path),  f"RF model eksik: {rf_path}")
            self.assertTrue(os.path.exists(xgb_path), f"XGB model eksik: {xgb_path}")
        print("TC-14 ✓ RF ve XGBoost modelleri mevcut")

    def test_tc14_rf_xgb_produce_scores(self):
        """TC-14: Her iki model de risk skoru üretiyor."""
        pid   = str(uuid.uuid4())
        meas  = make_measurements(pid, "sepsis")
        for condition in ["sepsis", "apnea", "cardiac"]:
            feats = self.service.preprocess(meas, condition)
            rf_path  = os.path.join(self.model_dir, f"model_rf_{condition}.pkl")
            xgb_path = os.path.join(self.model_dir, f"model_xgb_{condition}.pkl")
            with open(rf_path,  "rb") as f: rf_model  = pickle.load(f)
            with open(xgb_path, "rb") as f: xgb_model = pickle.load(f)
            feature_cols = self.service._get_feature_cols(condition)
            vec = np.array([feats.get(c, 0.0) for c in feature_cols], dtype=float).reshape(1, -1)
            rf_score  = float(rf_model.predict_proba(vec)[0][1])
            xgb_score = float(xgb_model.predict_proba(vec)[0][1])
            self.assertGreaterEqual(rf_score,  0.0); self.assertLessEqual(rf_score,  1.0)
            self.assertGreaterEqual(xgb_score, 0.0); self.assertLessEqual(xgb_score, 1.0)
        print("TC-14 ✓ RF ve XGBoost skorları üretiyor")

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
                self.assertIn("feature", item); self.assertIn("importance", item)
        print(f"TC-11 ✓ SHAP top-3: {[x['feature'] for x in result.shap_top3['sepsis']]}")

    def test_tc16_inference_returns_airesult(self):
        """TC-16: runInference AIResult döndürmeli."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(pid, make_measurements(pid, "sepsis"))
        self.assertIsInstance(result, AIResult)
        self.assertEqual(result.patientId, pid)
        self.assertIn(result.riskLevel, ["LOW", "MEDIUM", "HIGH"])
        print(f"TC-16 ✓ AIResult döndü: {result.getFormattedResult()}")

    def test_tc16_sepsis_detected(self):
        """TC-16: Sepsis senaryosunda yüksek risk skoru çıkmalı."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(pid, make_measurements(pid, "sepsis", ga=28, pna=10, pma=29.4))
        self.assertGreater(result.sepsis_score, 0.5, f"Sepsis skoru çok düşük: {result.sepsis_score}")
        print(f"TC-16 ✓ Sepsis algılandı: score={result.sepsis_score:.4f}")

    def test_tc16_healthy_low_risk(self):
        """TC-16: Sağlıklı senaryoda düşük sepsis skoru çıkmalı."""
        pid    = str(uuid.uuid4())
        result = self.service.runInference(pid, make_measurements(pid, "healthy", ga=35, pna=14, pma=37.0))
        self.assertLess(result.sepsis_score, 0.3, f"Sağlıklı hasta sepsis skoru yüksek: {result.sepsis_score}")
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

if __name__ == "__main__":
    print("=" * 60)
    print("Manifetch AI Modül Testi")
    print("=" * 60)
    unittest.main(verbosity=2)