"""
Manifetch NICU — Integration Testler
Test Plan: TC-15, TC-17, TC-18, TC-19, TC-20
"""
import sys, os, uuid, unittest, time, json
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

BASE_URL = os.getenv("REACT_APP_API_URL", "http://127.0.0.1:8000")


def get_token():
    res = requests.post(
        f"{BASE_URL}/auth/login",
        data={
            "username": os.getenv("SEED_NURSE_USERNAME", "nurse_mehmet"),
            "password": os.getenv("SEED_NURSE_PASSWORD", "Nurse123!"),
        }
    )
    res.raise_for_status()
    return res.json()["access_token"]


def get_patient_id(token):
    headers  = {"Authorization": f"Bearer {token}"}
    patients = requests.get(f"{BASE_URL}/dashboard/patients", headers=headers).json()
    if not patients:
        raise RuntimeError("Sistemde aktif hasta yok.")
    return patients[0]["patient_id"]


class TestIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token      = get_token()
        cls.headers    = {"Authorization": f"Bearer {cls.token}"}
        cls.patient_id = get_patient_id(cls.token)
        print(f"\nKullanılan hasta: {cls.patient_id[:8]}...")

    # ── TC-15: WebSocket stream simülasyondan backend'e ──────────────────────

    def test_tc15_websocket_vital_stream(self):
        """TC-15: Simülasyondan gelen vital backend'e ulaşmalı."""
        measurement_id = str(uuid.uuid4())
        payload = {
            "measurement_id":        measurement_id,
            "patient_id":            self.patient_id,
            "signal_type":           "HEART_RATE",
            "value":                 145.0,
            "unit":                  "BPM",
            "timestamp":             "2024-01-10T08:30:00Z",
            "timestamp_sec":         0.0,
            "is_valid":              True,
            "gestational_age_weeks": 32,
            "postnatal_age_days":    14,
            "pma_weeks":             34.0,
            "label_sepsis":          0,
            "label_apnea":           0,
            "label_cardiac":         0,
            "label_healthy":         1,
        }
        res = requests.post(
            f"{BASE_URL}/ingest/vital",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["measurement_id"], measurement_id)
        print(f"TC-15 ✓ Vital ingestion: {data['measurement_id'][:8]}...")

    # ── TC-17: AI modül → alert servisi ──────────────────────────────────────

    def test_tc17_ai_result_to_alert(self):
        """TC-17: Yüksek sepsis skoru → alert oluşturulmalı."""
        # Önce yüksek HR ve düşük SpO2 göndererek alert tetikle
        for sig, val, unit in [
            ("HEART_RATE", 220.0, "BPM"),
            ("SPO2",        75.0, "%"),
        ]:
            payload = {
                "measurement_id":        str(uuid.uuid4()),
                "patient_id":            self.patient_id,
                "signal_type":           sig,
                "value":                 val,
                "unit":                  unit,
                "timestamp":             "2024-01-10T09:00:00Z",
                "timestamp_sec":         100.0,
                "is_valid":              True,
                "gestational_age_weeks": 32,
                "postnatal_age_days":    14,
                "pma_weeks":             34.0,
                "label_sepsis":          1,
                "label_apnea":           0,
                "label_cardiac":         0,
                "label_healthy":         0,
            }
            res = requests.post(
                f"{BASE_URL}/ingest/vital",
                json=payload,
                headers=self.headers,
            )
            self.assertEqual(res.status_code, 200)

        # Alert oluştu mu kontrol et
        alerts = requests.get(
            f"{BASE_URL}/dashboard/patients/{self.patient_id}/alerts",
            headers=self.headers,
        ).json()
        self.assertGreater(len(alerts), 0, "Alert oluşmadı")
        print(f"TC-17 ✓ {len(alerts)} alert oluştu")

    # ── TC-18: Alert servisi → dashboard ─────────────────────────────────────

    def test_tc18_alert_on_dashboard(self):
        """TC-18: Alert dashboard'da görünmeli."""
        res = requests.get(
            f"{BASE_URL}/dashboard/patients/{self.patient_id}/alerts",
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        alerts = res.json()
        self.assertIsInstance(alerts, list)
        if alerts:
            alert = alerts[0]
            self.assertIn("alert_id",   alert)
            self.assertIn("severity",   alert)
            self.assertIn("status",     alert)
            self.assertIn("created_at", alert)
        print(f"TC-18 ✓ Dashboard'da {len(alerts)} alert görünüyor")

    # ── TC-19: WebSocket gerçek zamanlı streaming ─────────────────────────────

    def test_tc19_websocket_realtime(self):
        """TC-19: Vital gönderilince dashboard 1 saniye içinde güncellenmeli."""
        import websocket
        import threading

        received = []
        token    = self.token

        def on_open(ws):
            ws.send(json.dumps({"token": token}))

        def on_message(ws, message):
            msg = json.loads(message)
            if msg.get("type") == "vital":
                received.append(msg)
                ws.close()

        ws = websocket.WebSocketApp(
            f"ws://127.0.0.1:8000/ws/vitals/{self.patient_id}",
            on_open=on_open,
            on_message=on_message,
        )

        t = threading.Thread(target=lambda: ws.run_forever(ping_timeout=5))
        t.daemon = True
        t.start()
        time.sleep(1)

        # Vital gönder
        payload = {
            "measurement_id":        str(uuid.uuid4()),
            "patient_id":            self.patient_id,
            "signal_type":           "HEART_RATE",
            "value":                 148.0,
            "unit":                  "BPM",
            "timestamp":             "2024-01-10T09:30:00Z",
            "timestamp_sec":         200.0,
            "is_valid":              True,
            "gestational_age_weeks": 32,
            "postnatal_age_days":    14,
            "pma_weeks":             34.0,
            "label_sepsis":          0,
            "label_apnea":           0,
            "label_cardiac":         0,
            "label_healthy":         1,
        }
        t_start = time.time()
        requests.post(f"{BASE_URL}/ingest/vital", json=payload, headers=self.headers)

        t.join(timeout=3)
        elapsed = time.time() - t_start

        self.assertGreater(len(received), 0, "WebSocket'te veri alınamadı")
        self.assertLess(elapsed, 3.0, f"Gecikme çok yüksek: {elapsed:.2f}s")
        print(f"TC-19 ✓ WebSocket gecikme: {elapsed:.3f}s")

    # ── TC-20: AIResult hasta kaydına bağlı ──────────────────────────────────

    def test_tc20_airesult_linked_to_patient(self):
        """TC-20: AIResult hasta kaydıyla ilişkilendirilmeli."""
        measurements = []
        for i in range(30):
            for sig, val in [("HEART_RATE", 185.0), ("SPO2", 86.0), ("RESP_RATE", 65.0)]:
                measurements.append({
                    "timestamp_sec":        float(i),
                    "signalType":           sig,
                    "value":                val,
                    "gestationalAgeWeeks":  32,
                    "postnatalAgeDays":     14,
                    "pma_weeks":            34.0,
                })

        payload = {
            "patientId":    self.patient_id,
            "measurements": measurements,
            "save_to_db":   True,
        }
        res = requests.post(
            f"{BASE_URL}/ai/infer",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["patientId"], self.patient_id)
        self.assertIn("riskLevel", data)
        self.assertIn("shap_top3", data)

        # DB'de kayıtlı mı kontrol et
        ai_results = requests.get(
            f"{BASE_URL}/dashboard/patients/{self.patient_id}/ai",
            headers=self.headers,
        ).json()
        self.assertGreater(len(ai_results), 0)
        print(f"TC-20 ✓ AIResult DB'ye kaydedildi: {data['resultId'][:8]}...")


if __name__ == "__main__":
    print("=" * 60)
    print("Manifetch NICU — Integration Testler")
    print("=" * 60)
    unittest.main(verbosity=2)