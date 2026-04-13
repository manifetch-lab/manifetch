"""
Manifetch NICU — Performance Testler
Test Plan: TC-33, TC-34, TC-35, TC-37
"""
import sys, os, uuid, time, threading, unittest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


def make_measurements(patient_id, n=30):
    measurements = []
    for i in range(n):
        for sig, val in [("HEART_RATE", 185.0), ("SPO2", 86.0), ("RESP_RATE", 65.0)]:
            measurements.append({
                "timestamp_sec":        float(i),
                "signalType":           sig,
                "value":                val,
                "gestationalAgeWeeks":  32,
                "postnatalAgeDays":     14,
                "pma_weeks":            34.0,
            })
    return measurements


class TestPerformance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token      = get_token()
        cls.headers    = {"Authorization": f"Bearer {cls.token}"}
        cls.patient_id = get_patient_id(cls.token)
        print(f"\nKullanılan hasta: {cls.patient_id[:8]}...")

    # ── TC-33: 10 eşzamanlı AI inference ─────────────────────────────────────

    def test_tc33_concurrent_inference(self):
        """TC-33: 10 eşzamanlı inference 3 saniye içinde tamamlanmalı."""
        results  = []
        errors   = []
        threads  = []

        def run_inference():
            try:
                payload = {
                    "patientId":    self.patient_id,
                    "measurements": make_measurements(self.patient_id),
                    "save_to_db":   False,
                }
                t0  = time.time()
                res = requests.post(
                    f"{BASE_URL}/ai/infer",
                    json=payload,
                    headers=self.headers,
                    timeout=10,
                )
                elapsed = time.time() - t0
                if res.status_code == 200:
                    results.append(elapsed)
                else:
                    errors.append(res.status_code)
            except Exception as e:
                errors.append(str(e))

        t_start = time.time()
        for _ in range(10):
            t = threading.Thread(target=run_inference)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        total_elapsed = time.time() - t_start

        self.assertEqual(len(errors), 0, f"Hatalar: {errors}")
        self.assertEqual(len(results), 10, f"Sadece {len(results)}/10 tamamlandı")
        self.assertLess(total_elapsed, 3.0,
                        f"Toplam süre: {total_elapsed:.2f}s > 3s")

        avg = sum(results) / len(results)
        print(f"TC-33 ✓ 10 inference tamamlandı | "
              f"Toplam={total_elapsed:.2f}s | Ort={avg:.2f}s | "
              f"Maks={max(results):.2f}s")

    # ── TC-37: SHAP hesaplama süresi ──────────────────────────────────────────

    def test_tc37_shap_computation_time(self):
        """TC-37: SHAP değerleri 3 saniyelik inference bütçesi içinde hesaplanmalı."""
        payload = {
            "patientId":    self.patient_id,
            "measurements": make_measurements(self.patient_id),
            "save_to_db":   False,
        }

        t0  = time.time()
        res = requests.post(
            f"{BASE_URL}/ai/infer",
            json=payload,
            headers=self.headers,
            timeout=10,
        )
        elapsed = time.time() - t0

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("shap_top3", data)
        self.assertGreater(len(data["shap_top3"]), 0)
        self.assertLess(elapsed, 3.0, f"SHAP dahil inference: {elapsed:.2f}s > 3s")
        print(f"TC-37 ✓ SHAP dahil inference={elapsed:.3f}s")

    # ── TC-34: Gerçek zamanlı güncelleme gecikmesi ────────────────────────────

    def test_tc34_realtime_latency(self):
        """TC-34: 10 eşzamanlı WebSocket stream, her biri 1 saniye içinde güncellenmeli."""
        import websocket as ws_client

        received  = {}
        errors    = []
        latencies = []

        def ws_connect(idx):
            token = self.token
            msgs  = []

            def on_open(ws):
                ws.send(__import__("json").dumps({"token": token}))

            def on_message(ws, message):
                msg = __import__("json").loads(message)
                if msg.get("type") == "vital":
                    msgs.append(time.time())
                    ws.close()

            try:
                w = ws_client.WebSocketApp(
                    f"ws://127.0.0.1:8000/ws/vitals/{self.patient_id}",
                    on_open=on_open,
                    on_message=on_message,
                )
                w.run_forever(ping_timeout=5)
                received[idx] = msgs
            except Exception as e:
                errors.append(str(e))

        # 10 WebSocket bağlantısı aç
        threads = []
        for i in range(10):
            t = threading.Thread(target=ws_connect, args=(i,))
            threads.append(t)
            t.start()

        time.sleep(1)

        # Vital gönder ve zamanı kaydet
        t_send = time.time()
        payload = {
            "measurement_id":        str(uuid.uuid4()),
            "patient_id":            self.patient_id,
            "signal_type":           "HEART_RATE",
            "value":                 150.0,
            "unit":                  "BPM",
            "timestamp":             "2024-01-10T10:00:00Z",
            "timestamp_sec":         300.0,
            "is_valid":              True,
            "gestational_age_weeks": 32,
            "postnatal_age_days":    14,
            "pma_weeks":             34.0,
            "label_sepsis":          0,
            "label_apnea":           0,
            "label_cardiac":         0,
            "label_healthy":         1,
        }
        requests.post(f"{BASE_URL}/ingest/vital", json=payload, headers=self.headers)

        for t in threads:
            t.join(timeout=5)

        for idx, msgs in received.items():
            if msgs:
                latency = msgs[0] - t_send
                latencies.append(latency)

        self.assertGreater(len(latencies), 0, "Hiç WebSocket mesajı alınamadı")

        max_latency = max(latencies)
        self.assertLess(max_latency, 1.0,
                        f"Maks gecikme: {max_latency:.3f}s > 1s")

        print(f"TC-34 ✓ {len(latencies)}/10 WebSocket aldı | "
              f"Ort={sum(latencies)/len(latencies):.3f}s | "
              f"Maks={max_latency:.3f}s")

    # ── TC-35: 10 eşzamanlı stream stabilitesi ───────────────────────────────

    def test_tc35_concurrent_stream_stability(self):
        """TC-35: 10 eşzamanlı stream 30 saniye boyunca stabil kalmalı."""
        errors    = []
        sent      = []
        lock      = threading.Lock()
        stop_flag = threading.Event()

        def stream_vitals(idx):
            s = 0
            while not stop_flag.is_set():
                payload = {
                    "measurement_id":        str(uuid.uuid4()),
                    "patient_id":            self.patient_id,
                    "signal_type":           "HEART_RATE",
                    "value":                 145.0 + idx,
                    "unit":                  "BPM",
                    "timestamp":             "2024-01-10T10:00:00Z",
                    "timestamp_sec":         float(s),
                    "is_valid":              True,
                    "gestational_age_weeks": 32,
                    "postnatal_age_days":    14,
                    "pma_weeks":             34.0,
                    "label_sepsis":          0,
                    "label_apnea":           0,
                    "label_cardiac":         0,
                    "label_healthy":         1,
                }
                try:
                    res = requests.post(
                        f"{BASE_URL}/ingest/vital",
                        json=payload,
                        headers=self.headers,
                        timeout=2,
                    )
                    if res.status_code == 200:
                        with lock:
                            sent.append(1)
                    else:
                        with lock:
                            errors.append(res.status_code)
                except Exception as e:
                    with lock:
                        errors.append(str(e))
                s += 1
                time.sleep(1)

        threads = []
        for i in range(10):
            t = threading.Thread(target=stream_vitals, args=(i,))
            t.daemon = True
            threads.append(t)
            t.start()

        # 30 saniye çalıştır
        print("\n  TC-35: 30 saniye bekleniyor...")
        time.sleep(30)
        stop_flag.set()

        for t in threads:
            t.join(timeout=5)

        total_sent   = len(sent)
        total_errors = len(errors)
        error_rate   = total_errors / max(total_sent + total_errors, 1)

        self.assertLess(error_rate, 0.05,
                        f"Hata oranı: {error_rate:.1%} > %5")
        self.assertGreater(total_sent, 0, "Hiç ölçüm gönderilemedi")

        print(f"TC-35 ✓ {total_sent} ölçüm | {total_errors} hata | "
              f"Hata oranı: {error_rate:.1%}")


if __name__ == "__main__":
    print("=" * 60)
    print("Manifetch NICU — Performance Testler")
    print("=" * 60)
    unittest.main(verbosity=2)