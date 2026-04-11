import argparse, time, uuid, requests, threading, json
from datetime import datetime, timezone
from collections import deque
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_simulation.generator import (
    get_baseline, compute_pma,
    build_sepsis_schedule, build_apnea_schedule, build_cardiac_schedule,
    build_ecg_waveform,
    sepsis_delta, apnea_delta, cardiac_delta, clamp,
)
import numpy as np


BASE_URL   = os.getenv("REACT_APP_API_URL", "http://127.0.0.1:8000")
LOGIN_URL  = f"{BASE_URL}/auth/login"
INGEST_URL = f"{BASE_URL}/ingest/vital"
INFER_URL  = f"{BASE_URL}/ai/infer"
ECG_URL    = f"{BASE_URL}/ingest/ecg"
ECG_HZ     = 25
AI_INTERVAL_SEC = 30   # Her 30 saniyede bir AI inference


def login(username, password):
    res = requests.post(LOGIN_URL, data={"username": username, "password": password})
    res.raise_for_status()
    print(f"[Auth] Giriş başarılı: {username}")
    return res.json()["access_token"]


def list_patients(token):
    headers  = {"Authorization": f"Bearer {token}"}
    patients = requests.get(f"{BASE_URL}/dashboard/patients", headers=headers).json()
    if not patients:
        print("Sistemde aktif hasta yok. Önce frontend'den hasta ekleyin.")
        return
    print(f"\n{'─'*65}")
    print(f"  {'AD':<28} {'GA':>4} {'PNA':>4}  ID")
    print(f"{'─'*65}")
    for p in patients:
        print(f"  {p['full_name']:<28} {p['gestational_age_weeks']:>3}w "
              f"{p['postnatal_age_days']:>3}d  {p['patient_id']}")
    print(f"{'─'*65}\n")


def get_patient(token, patient_id):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{BASE_URL}/dashboard/patients/{patient_id}", headers=headers)
    if res.status_code == 404:
        print(f"[HATA] Hasta bulunamadı: {patient_id}")
        return None
    res.raise_for_status()
    return res.json()


def build_schedules(scenario, ga_weeks, pna_days, pma_weeks, duration_sec, seed):
    sched_rng = np.random.default_rng(seed + 99999)
    baseline  = get_baseline(ga_weeks)
    onset_sec = int(np.random.default_rng(seed).uniform(60, 300))

    if scenario == "normal":
        return {}, {}, {}, []
    elif scenario == "sepsis":
        return build_sepsis_schedule(onset_sec, duration_sec, baseline, sched_rng), {}, {}, ["sepsis"]
    elif scenario == "apnea":
        if ga_weeks >= 36:
            print(f"  UYARI: GA={ga_weeks}w için apnea riski düşük, GA=30w kullanılıyor.")
            ga_weeks = 30
        apn = build_apnea_schedule(ga_weeks, pna_days, pma_weeks, onset_sec, duration_sec, sched_rng)
        return {}, apn, {}, ["apnea"]
    elif scenario == "cardiac":
        card = build_cardiac_schedule(onset_sec, duration_sec, "svt", sched_rng, ga_weeks)
        return {}, {}, card, ["cardiac"]
    else:
        sep  = build_sepsis_schedule(onset_sec, duration_sec, baseline, sched_rng)
        card = build_cardiac_schedule(onset_sec + 60, duration_sec, "bradyarrhythmia", sched_rng, ga_weeks)
        return sep, {}, card, ["sepsis", "cardiac"]


def run_ai_inference(token, patient_id, measurement_buffer, ga_weeks, pna_days, pma_weeks):
    """Son 30 saniyelik ölçümlerle AI inference çalıştır ve sonucu kaydet."""
    headers = {"Authorization": f"Bearer {token}"}
    if len(measurement_buffer) < 10:
        return

    measurements = list(measurement_buffer)
    payload = {
        "patientId":    patient_id,
        "measurements": measurements,
        "save_to_db":   True,
    }
    try:
        res = requests.post(INFER_URL, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            result = res.json()
            print(f"\n  🤖 AI: [{result['riskLevel']}] "
                  f"Sepsis={result['sepsis_score']:.2f} "
                  f"Apnea={result['apnea_score']:.2f} "
                  f"Cardiac={result['cardiac_score']:.2f}")
        else:
            print(f"\n  [AI] Hata: {res.status_code}")
    except Exception as e:
        print(f"\n  [AI] İstek hatası: {e}")


def stream_patient(token, patient, scenario, duration_min, speed, seed):
    headers      = {"Authorization": f"Bearer {token}"}
    patient_id   = patient["patient_id"]
    ga_weeks     = patient["gestational_age_weeks"]
    pna_days     = patient["postnatal_age_days"]
    pma_weeks    = compute_pma(ga_weeks, pna_days)
    baseline     = get_baseline(ga_weeks)
    duration_sec = duration_min * 60

    sep_sched, apn_sched, card_sched, diseases = build_schedules(
        scenario, ga_weeks, pna_days, pma_weeks, duration_sec, seed
    )
    is_healthy = not bool(diseases)
    bnf = 1.5 if pna_days <= 7 else 1.2 if pna_days <= 14 else 1.0

    print(f"\n{'='*60}")
    print(f"  Hasta  : {patient['full_name']}")
    print(f"  ID     : {patient_id[:8]}...")
    print(f"  GA/PNA : {ga_weeks}w / {pna_days}d")
    print(f"  Senaryo: {scenario.upper()} {diseases}")
    print(f"  Süre   : {duration_min}dk | Hız: {speed}x | Ctrl+C durdurur")
    print(f"  AI     : Her {AI_INTERVAL_SEC}s otomatik inference")
    print(f"  ECG    : HTTP POST → WebSocket broadcast (25 Hz)")
    print(f"{'='*60}\n")

    # ECG waveform önceden üret
    ecg_signal = build_ecg_waveform(
        duration_sec, baseline, card_sched, apn_sched, sep_sched, ga_weeks, seed
    )



    sleep_time = 1.0 / speed
    sent = errors = alerts_total = 0
    last_ai_sec = -AI_INTERVAL_SEC

    # AI için ölçüm buffer — son 30 saniyelik
    measurement_buffer = deque(maxlen=90)  # HR + SPO2 + RR = ~3 ölçüm/sn

    for s in range(duration_sec):
        rng_s = np.random.default_rng(seed + s * 7)
        ts    = datetime.now(timezone.utc).isoformat()

        hr   = baseline["hr_mean"]   + rng_s.normal(0, baseline["hr_std"]   * 0.2 * bnf)
        spo2 = baseline["spo2_mean"] + rng_s.normal(0, baseline["spo2_std"] * 0.2 * bnf)
        rr   = baseline["rr_mean"]   + rng_s.normal(0, baseline["rr_std"]   * 0.2 * bnf)

        label_s = label_a = label_c = 0

        if sep_sched:
            d = sepsis_delta(sep_sched, s, baseline, rng_s, ga_weeks, pna_days)
            hr += d["hr"]; spo2 += d["spo2"]; rr += d["rr"]; label_s = d["label"]
        if apn_sched:
            d = apnea_delta(apn_sched, s, baseline, rng_s)
            hr += d["hr"]; spo2 += d["spo2"]; rr += d["rr"]; label_a = d["label"]
        if card_sched:
            d = cardiac_delta(card_sched, s, rng_s)
            hr += d["hr"]; spo2 += d["spo2"]; rr += d["rr"]; label_c = d["label"]

        hr   = round(clamp(hr,   50, 280), 1)
        spo2 = round(clamp(spo2, 65, 100), 1)
        rr   = round(clamp(rr,   0,  90),  1)
        label_h = 1 if is_healthy else 0

        common = {
            "patient_id": patient_id, "stream_id": None,
            "timestamp": ts, "timestamp_sec": float(s),
            "gestational_age_weeks": ga_weeks, "postnatal_age_days": pna_days,
            "pma_weeks": pma_weeks, "is_valid": True,
            "label_sepsis": label_s, "label_apnea": label_a,
            "label_cardiac": label_c, "label_healthy": label_h,
        }

        # HR, SpO2, RR → HTTP POST
        for sig, val, unit in [
            ("HEART_RATE", hr,   "BPM"),
            ("SPO2",       spo2, "%"),
            ("RESP_RATE",  rr,   "breaths/min"),
        ]:
            if sig == "RESP_RATE" and s % 2 != 0:
                continue
            payload = {**common, "measurement_id": str(uuid.uuid4()),
                       "signal_type": sig, "value": val, "unit": unit}
            try:
                res = requests.post(INGEST_URL, json=payload, headers=headers, timeout=2)
                if res.status_code == 200:
                    sent += 1
                    n = res.json().get("alerts_triggered", 0)
                    if n > 0:
                        alerts_total += n
                        print(f"  ⚠  [{s:5d}s] ALERT! {sig}={val} → {n} yeni alert")
                else:
                    errors += 1
            except:
                errors += 1

            # AI buffer'a ekle
            measurement_buffer.append({
                "timestamp_sec":       float(s),
                "signalType":          sig,
                "value":               val,
                "gestationalAgeWeeks": ga_weeks,
                "postnatalAgeDays":    pna_days,
                "pma_weeks":           pma_weeks,
            })


        # ECG → HTTP POST /ingest/ecg → backend → WebSocket broadcast → frontend
        if s * ECG_HZ < len(ecg_signal):
            try:
                start_idx = s * ECG_HZ
                end_idx   = min(start_idx + ECG_HZ, len(ecg_signal))
                samples   = ecg_signal[start_idx:end_idx].tolist()
                requests.post(ECG_URL, json={
                    "patient_id": patient_id,
                    "samples":    samples,
                    "timestamp":  ts,
                    "fs":         ECG_HZ,
                }, headers=headers, timeout=1)
            except Exception:
                pass

        # AI inference — her AI_INTERVAL_SEC saniyede bir
        if s - last_ai_sec >= AI_INTERVAL_SEC and len(measurement_buffer) >= 10:
            last_ai_sec = s
            ai_thread = threading.Thread(
                target=run_ai_inference,
                args=(token, patient_id, list(measurement_buffer),
                      ga_weeks, pna_days, pma_weeks),
                daemon=True,
            )
            ai_thread.start()

        if s % 10 == 0:
            print(f"  [{s:5d}s] HR={hr:5.1f}  SpO2={spo2:5.1f}%  RR={rr:4.1f}  "
                  f"| ✓{sent} ✗{errors} ⚠{alerts_total}")

        time.sleep(sleep_time)

    print(f"\n[Stream] Tamamlandı — {sent} ölçüm, {errors} hata, {alerts_total} alert")


def main():
    parser = argparse.ArgumentParser(description="Manifetch NICU Stream Runner v2")
    parser.add_argument("--patient_id", type=str, default=None)
    parser.add_argument("--scenario",   default="normal",
                        choices=["normal", "sepsis", "apnea", "cardiac", "mixed"])
    parser.add_argument("--duration",   type=int,   default=60)
    parser.add_argument("--speed",      type=float, default=1.0)
    parser.add_argument("--seed",       type=int,   default=42)
    parser.add_argument("--username", type=str, default=os.getenv("SEED_NURSE_USERNAME", "nurse_mehmet"))
    parser.add_argument("--password", type=str, default=os.getenv("SEED_NURSE_PASSWORD", "Nurse123!"))
    parser.add_argument("--list",       action="store_true")
    args = parser.parse_args()

    try:
        token = login(args.username, args.password)
    except Exception as e:
        print(f"[HATA] Login başarısız: {e}")
        return

    if args.list:
        list_patients(token)
        return

    if not args.patient_id:
        print("\n[HATA] --patient_id gerekli!")
        list_patients(token)
        return

    patient = get_patient(token, args.patient_id)
    if not patient:
        return

    try:
        stream_patient(token, patient, args.scenario, args.duration, args.speed, args.seed)
    except KeyboardInterrupt:
        print("\n[Stream] Durduruldu.")


if __name__ == "__main__":
    main()