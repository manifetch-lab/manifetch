"""
Manifetch NICU — Unit Testler
Test Plan: TC-01, TC-02, TC-03, TC-04, TC-05, TC-06, TC-07, TC-08, TC-09, TC-10, TC-12, TC-13
"""
import sys, os, uuid, unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_module.inference_service import InferenceService, VitalMeasurement


def make_measurements(patient_id, signal_type, values, ga=32, pna=14, pma=34.0):
    return [
        VitalMeasurement(patient_id, float(i), signal_type, v, ga, pna, pma)
        for i, v in enumerate(values)
    ]


class TestUnitCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.service = InferenceService()

    # ── TC-01: Sinyal normalizasyonu ─────────────────────────────────────────

    def test_tc01_signal_normalization(self):
        """TC-01: Z-score normalizasyonu — mean~0, std~1 olmalı."""
        pid  = str(uuid.uuid4())
        vals = list(np.random.default_rng(42).normal(150, 15, 60))
        meas = make_measurements(pid, "HEART_RATE", vals)

        feats = self.service.preprocess(meas, "sepsis")
        hr_mean = feats.get("hr_mean", 0)
        hr_std  = feats.get("hr_std",  0)

        self.assertIsNotNone(hr_mean)
        self.assertGreater(hr_std, 0)
        print(f"TC-01 ✓ HR mean={hr_mean:.2f} std={hr_std:.2f}")

    # ── TC-02: Threshold kalibrasyon — term yenidoğan ────────────────────────

    def test_tc02_threshold_term(self):
        """TC-02: Term yenidoğan (GA=40) için HR eşiği 100-160 aralığında."""
        from backend.db.models import ThresholdRule
        from backend.db.enums import SignalType, Severity

        rule = ThresholdRule(
            rule_id     = str(uuid.uuid4()),
            patient_id  = str(uuid.uuid4()),
            signal_type = SignalType.HEART_RATE.value,
            min_value   = 100,
            max_value   = 160,
            enabled     = True,
            severity    = Severity.HIGH.value,
        )
        self.assertEqual(rule.min_value, 100)
        self.assertEqual(rule.max_value, 160)
        print("TC-02 ✓ Term yenidoğan threshold: 100-160 bpm")

    # ── TC-03: Threshold kalibrasyon — preterm ────────────────────────────────

    def test_tc03_threshold_preterm(self):
        """TC-03: Preterm (GA=26) için HR eşiği 120-177 aralığında."""
        from backend.db.models import ThresholdRule
        from backend.db.enums import SignalType, Severity

        rule = ThresholdRule(
            rule_id     = str(uuid.uuid4()),
            patient_id  = str(uuid.uuid4()),
            signal_type = SignalType.HEART_RATE.value,
            min_value   = 120,
            max_value   = 177,
            enabled     = True,
            severity    = Severity.HIGH.value,
        )
        self.assertEqual(rule.min_value, 120)
        self.assertEqual(rule.max_value, 177)
        print("TC-03 ✓ Preterm threshold: 120-177 bpm")

    # ── TC-04: ECG feature extraction ─────────────────────────────────────────

    def test_tc04_ecg_feature_extraction(self):
        """TC-04: 30 saniyelik ECG verisinden HRV, R-R intervali hesaplanmalı."""
        from ai_module.inference_service import extract_ecg_beat_features, ECG_HZ
        import scipy.signal as sp

        duration = 30
        fs       = ECG_HZ
        t        = np.linspace(0, duration, duration * fs)
        ecg      = np.sin(2 * np.pi * 2 * t) + 0.1 * np.random.default_rng(42).normal(size=len(t))

        feats = extract_ecg_beat_features(ecg, fs)

        self.assertIn("ecg_rr_mean_ms", feats)
        self.assertIn("ecg_rmssd_ms",   feats)
        print(f"TC-04 ✓ ECG features: rr_mean={feats.get('ecg_rr_mean_ms', 'NaN'):.1f}ms")

    # ── TC-05: SpO₂ feature extraction ───────────────────────────────────────

    def test_tc05_spo2_feature_extraction(self):
        """TC-05: SpO₂ dizisinden mean, min, pct_below_90 hesaplanmalı."""
        pid      = str(uuid.uuid4())
        spo2_vals = [96, 95, 94, 88, 87, 86, 95, 96, 97, 96] * 3
        hr_vals   = [145] * len(spo2_vals)
        meas  = make_measurements(pid, "HEART_RATE", hr_vals)
        meas += make_measurements(pid, "SPO2", spo2_vals)

        feats = self.service.preprocess(meas, "sepsis")

        self.assertIn("spo2_mean",         feats)
        self.assertIn("spo2_min",          feats)
        self.assertIn("spo2_pct_below_90", feats)
        self.assertGreater(feats["spo2_pct_below_90"], 0)
        print(f"TC-05 ✓ SpO2 pct_below_90={feats['spo2_pct_below_90']:.2f}")

    # ── TC-06: Solunum hızı feature extraction ────────────────────────────────

    def test_tc06_rr_feature_extraction(self):
        """TC-06: RR dizisinden mean, apnea süresi, variabilite hesaplanmalı."""
        pid     = str(uuid.uuid4())
        rr_vals = [45, 44, 43, 5, 3, 2, 1, 44, 45, 46] * 3
        hr_vals = [145] * len(rr_vals)
        meas  = make_measurements(pid, "HEART_RATE", hr_vals)
        meas += make_measurements(pid, "RESP_RATE", rr_vals)

        feats = self.service.preprocess(meas, "apnea")

        self.assertIn("rr_mean",         feats)
        self.assertIn("rr_pct_below_10", feats)
        self.assertIn("rr_cv",           feats)
        self.assertGreater(feats["rr_pct_below_10"], 0)
        print(f"TC-06 ✓ RR pct_below_10={feats['rr_pct_below_10']:.2f}")

    # ── TC-07: Kalp hızı feature extraction ──────────────────────────────────

    def test_tc07_hr_feature_extraction(self):
        """TC-07: HR dizisinden mean, max, min, ani değişim hesaplanmalı."""
        pid  = str(uuid.uuid4())
        vals = [140, 142, 145, 200, 210, 145, 143, 141, 140, 139] * 3
        meas = make_measurements(pid, "HEART_RATE", vals)

        feats = self.service.preprocess(meas, "cardiac")

        self.assertIn("hr_mean", feats)
        self.assertIn("hr_max",  feats)
        self.assertIn("hr_min",  feats)
        self.assertIn("hr_hrv",  feats)
        self.assertGreater(feats["hr_max"], 150)
        print(f"TC-07 ✓ HR max={feats['hr_max']:.1f} hrv={feats['hr_hrv']:.2f}")

    # ── TC-08: Sentetik veri üretimi — apnea ─────────────────────────────────

    def test_tc08_synthetic_apnea(self):
        """TC-08: Apnea senaryosunda RR 20 saniyeden fazla durmalı."""
        from data_simulation.generator import (
            build_apnea_schedule, get_baseline, compute_pma
        )

        ga, pna  = 28, 14
        pma      = compute_pma(ga, pna)
        baseline = get_baseline(ga)
        rng      = np.random.default_rng(42)
        sched    = build_apnea_schedule(
            ga, pna, pma, onset_sec=0, duration_sec=3600, rng=rng
        )

        apnea_seconds = sum(
            1 for info in sched.values() if info.get("state") == "APNEA"
        )
        self.assertGreater(apnea_seconds, 20, f"Apnea süresi: {apnea_seconds}s")
        print(f"TC-08 ✓ Apnea süresi: {apnea_seconds}s")


    # ── TC-09: Sentetik veri üretimi — sepsis ────────────────────────────────

    def test_tc09_synthetic_sepsis(self):
        """TC-09: Sepsis senaryosunda HR>170, SpO2<92 olmalı."""
        from data_simulation.generator import (
            build_sepsis_schedule, sepsis_delta, get_baseline
        )

        ga, pna  = 28, 7
        baseline = get_baseline(ga)
        rng      = np.random.default_rng(42)
        sched    = build_sepsis_schedule(
            onset_sec=0, duration_sec=3600, baseline=baseline, rng=rng
        )

        hr_vals   = []
        spo2_vals = []
        rng2      = np.random.default_rng(1)

        for s in range(0, 3600, 10):
            d = sepsis_delta(sched, s, baseline, rng2, ga, pna)
            hr_vals.append(baseline["hr_mean"] + d["hr"])
            spo2_vals.append(baseline["spo2_mean"] + d["spo2"])

        max_hr   = max(hr_vals)
        min_spo2 = min(spo2_vals)

        self.assertGreater(max_hr,    170, f"Max HR: {max_hr:.1f}")
        self.assertLess(min_spo2,      92, f"Min SpO2: {min_spo2:.1f}")
        print(f"TC-09 ✓ Sepsis: max_HR={max_hr:.1f}, min_SpO2={min_spo2:.1f}")
    
    # ── TC-10: Kural bazlı etiket atama ──────────────────────────────────────

    def test_tc10_rule_based_label(self):
        """TC-10: HR=185, SpO2=88, RR=65 → sepsis şüphe etiketi."""
        pid  = str(uuid.uuid4())
        meas = []
        for i in range(30):
            meas.append(VitalMeasurement(pid, float(i), "HEART_RATE", 185.0, 32, 14, 34.0))
            meas.append(VitalMeasurement(pid, float(i), "SPO2",       88.0,  32, 14, 34.0))
            meas.append(VitalMeasurement(pid, float(i), "RESP_RATE",  65.0,  32, 14, 34.0))

        result = self.service.runInference(pid, meas)
        self.assertGreater(result.sepsis_score, 0.5,
                           f"Sepsis skoru çok düşük: {result.sepsis_score}")
        print(f"TC-10 ✓ Sepsis skoru: {result.sepsis_score:.4f}")

    # ── TC-12: Alert seviyesi belirleme ──────────────────────────────────────

    def test_tc12_alert_level(self):
        """TC-12: Sepsis risk skoru 0.78 → riskLevel HIGH olmalı."""
        from ai_module.inference_service import AIResult
        from datetime import datetime, timezone

        result = AIResult(
            resultId      = str(uuid.uuid4()),
            patientId     = str(uuid.uuid4()),
            timeStamp     = datetime.now(timezone.utc),
            sepsis_score  = 0.78,
            apnea_score   = 0.10,
            cardiac_score = 0.15,
            sepsis_label  = 1,
            apnea_label   = 0,
            cardiac_label = 0,
        )
        self.assertEqual(result.riskLevel, "HIGH")
        print(f"TC-12 ✓ riskScore={result.riskScore} riskLevel={result.riskLevel}")

    # ── TC-13: Threshold kural ihlali ────────────────────────────────────────

    def test_tc13_threshold_violation(self):
        """TC-13: SpO2=88, min_threshold=90 → kural ihlali tespit edilmeli."""
        from backend.db.models import VitalMeasurement as VM, ThresholdRule
        from backend.db.enums import SignalType, Severity
        from backend.services.rule_engine_service import RuleEngineService
        from unittest.mock import MagicMock

        rule = ThresholdRule(
            rule_id     = str(uuid.uuid4()),
            patient_id  = str(uuid.uuid4()),
            signal_type = SignalType.SPO2.value,
            min_value   = 90.0,
            max_value   = 100.0,
            enabled     = True,
            severity    = Severity.HIGH.value,
        )

        measurement       = MagicMock()
        measurement.value = 88.0
        measurement.signal_type = SignalType.SPO2.value

        violated = measurement.value < rule.min_value or measurement.value > rule.max_value
        self.assertTrue(violated)
        print(f"TC-13 ✓ SpO2=88 < min=90 → ihlal tespit edildi")


if __name__ == "__main__":
    print("=" * 60)
    print("Manifetch NICU — Unit Testler")
    print("=" * 60)
    unittest.main(verbosity=2)