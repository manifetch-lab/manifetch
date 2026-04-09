"""
Manifetch NICU — Real-Time Stream Publisher
============================================
LLD: StreamPublisher sinifi

CSV'den okunan sentetik vital verileri backend API'ye POST'lar.
Backend her mesajda: DB yaz + threshold kontrol + alert + WebSocket push yapar.
Frontend otomatik olarak canli veriyi WebSocket'ten gorur.

Kullanim:
  python stream_publisher.py                          # 50x hiz, 10 bebek
  python stream_publisher.py --speed 1                # gercek zamanli
  python stream_publisher.py --speed 100 --limit 500  # hizli test, 500 olcum/bebek

Mimari:
  CSV --> StreamPublisher.publish() --> POST /ingest/vital --> Backend
                                                                |
                                                         DB + WebSocket + Alert + AI
                                                                |
                                                            Frontend
"""

import asyncio
import csv
import time
import argparse
from collections import defaultdict
from typing import Optional

import aiohttp

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

SIGNAL_UNITS = {
    "HEART_RATE": "BPM",
    "SPO2":       "%",
    "RESP_RATE":  "breaths/min",
    "ECG":        "mV",
}


class StreamPublisher:
    """
    LLD: StreamPublisher
    Attributes:
        speed_factor: float   — replay hiz carpani (1=gercek zaman)
        limit:        int     — hasta basina max olcum (0=tumu)
        api_base:     str     — backend API adresi
    Methods:
        load(csv_path)        — CSV verisini yukle ve hasta bazli grupla
        publish()             — tum hastalari paralel olarak backend'e gonder
        publish_patient(pid)  — tek hasta verilerini zamanlamali gonder
    """

    def __init__(
        self,
        csv_path:     str   = "data/all_data/all_vitals.csv",
        speed_factor: float = 50.0,
        limit:        int   = 0,
        concurrency:  int   = 50,
        api_base:     str   = "http://127.0.0.1:8000",
    ):
        self.csv_path     = csv_path
        self.speed_factor = speed_factor
        self.limit        = limit
        self.concurrency  = concurrency
        self.api_base     = api_base
        self.ingest_url   = f"{api_base}/ingest/vital"

        # Hasta bazli veri: {patient_id: [row, ...]}
        self._patients: dict[str, list[dict]] = {}

        # Istatistik
        self.total_sent     = 0
        self.total_errors   = 0
        self.total_alerts   = 0

        # Print lock (thread-safe log)
        self._print_lock = asyncio.Lock()

    # ── Veri yukleme ─────────────────────────────────────────────────────

    def load(self, csv_path: Optional[str] = None) -> int:
        """
        CSV'yi oku, patient_id bazinda grupla, timestamp_sec'e gore sirala.
        Donuş: toplam hasta sayisi.
        """
        path = csv_path or self.csv_path
        patients: dict[str, list[dict]] = defaultdict(list)

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("isValid", "True").strip().lower() != "true":
                    continue
                patients[row["patientId"]].append(row)

        for pid in patients:
            patients[pid].sort(key=lambda r: float(r["timestamp_sec"]))

        self._patients = dict(patients)
        return len(self._patients)

    # ── Payload olusturma ────────────────────────────────────────────────

    @staticmethod
    def _build_payload(row: dict) -> dict:
        """CSV satirindan /ingest/vital payload'u olustur."""
        import uuid
        return {
            "measurement_id":        str(uuid.uuid4()),
            "patient_id":            row["patientId"],
            "signal_type":           row["signalType"],
            "value":                 float(row["value"]),
            "unit":                  SIGNAL_UNITS.get(row["signalType"], ""),
            "timestamp":             row["timestamp"],
            "timestamp_sec":         float(row["timestamp_sec"]),
            "is_valid":              True,
            "gestational_age_weeks": int(row["gestationalAgeWeeks"]),
            "postnatal_age_days":    int(row["postnatalAgeDays"]),
            "pma_weeks":             float(row["pma_weeks"]),
            "label_sepsis":          int(row["label_sepsis"]),
            "label_apnea":           int(row["label_apnea"]),
            "label_cardiac":         int(row["label_cardiac"]),
            "label_healthy":         int(row.get("label_healthy", 0)),
        }

    # ── Loglama ──────────────────────────────────────────────────────────

    async def _log(self, baby_id: str, msg: str, color: str = RESET):
        async with self._print_lock:
            short = baby_id[:8]
            print(f"{color}[{short}] {msg}{RESET}")

    # ── Tek hasta yayini ─────────────────────────────────────────────────

    async def publish_patient(
        self,
        session:    aiohttp.ClientSession,
        patient_id: str,
        rows:       list[dict],
    ):
        """
        LLD: StreamPublisher.publish_patient(pid)
        Bir hastanin verilerini zamanlama ile backend'e POST'lar.
        """
        total = min(len(rows), self.limit) if self.limit > 0 else len(rows)
        sent = 0
        alerts_triggered = 0
        errors = 0
        prev_ts = None

        await self._log(patient_id, f"Basladi — {total} olcum gonderilecek", CYAN)

        for row in rows[:total]:
            ts = float(row["timestamp_sec"])

            # Zamanlamali bekleme — gercek zamani simule et
            if prev_ts is not None:
                gap = (ts - prev_ts) / self.speed_factor
                if gap > 0:
                    await asyncio.sleep(gap)
            prev_ts = ts

            payload = self._build_payload(row)

            try:
                async with session.post(self.ingest_url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sent += 1
                        n_alerts = data.get("alerts_triggered", 0)
                        alerts_triggered += n_alerts

                        if sent % 100 == 0:
                            await self._log(patient_id,
                                f"t={ts:.0f}s  sent={sent}/{total}  "
                                f"alerts={alerts_triggered}  "
                                f"{row['signalType']}={float(row['value']):.1f}",
                                GREEN)
                        if n_alerts > 0:
                            await self._log(patient_id,
                                f"ALERT! t={ts:.0f}s  "
                                f"{row['signalType']}={float(row['value']):.1f}  "
                                f"alerts={data.get('alerts', [])}",
                                RED)
                    else:
                        errors += 1
                        if errors <= 3:
                            body = await resp.text()
                            await self._log(patient_id,
                                f"HTTP {resp.status}: {body[:120]}", YELLOW)
            except Exception as e:
                errors += 1
                if errors <= 3:
                    await self._log(patient_id, f"Hata: {e}", RED)

        self.total_sent   += sent
        self.total_errors += errors
        self.total_alerts += alerts_triggered

        await self._log(patient_id,
            f"Bitti — {sent} gonderildi, {alerts_triggered} alert, {errors} hata",
            CYAN)

    # ── Tum hastalari paralel yayinla ────────────────────────────────────

    async def publish(self):
        """
        LLD: StreamPublisher.publish()
        Tum hastalari paralel async task'larla backend'e gonderir.
        """
        if not self._patients:
            self.load()

        print(f"{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}  Manifetch NICU Stream Publisher{RESET}")
        print(f"{BOLD}  Hiz: {self.speed_factor}x  |  Limit: {self.limit or 'tumu'}  "
              f"|  Hastalar: {len(self._patients)}{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        for pid, rows in self._patients.items():
            signals = defaultdict(int)
            for r in rows:
                signals[r["signalType"]] += 1
            signal_str = "  ".join(f"{k}:{v}" for k, v in signals.items())
            print(f"  {pid[:8]}  {len(rows):>6} olcum  ({signal_str})")
        print()

        # Backend saglik kontrolu
        connector = aiohttp.TCPConnector(limit=self.concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.get(f"{self.api_base}/health") as resp:
                    if resp.status != 200:
                        print(f"{RED}Backend saglik kontrolu basarisiz: HTTP {resp.status}{RESET}")
                        return
            except aiohttp.ClientError as e:
                print(f"{RED}Backend'e baglanilamiyor ({self.api_base}): {e}{RESET}")
                print("Once backend'i baslatin: uvicorn backend.main:app --reload")
                return

            print(f"{GREEN}Backend baglantisi OK{RESET}\n")

            t0 = time.time()

            tasks = [
                asyncio.create_task(
                    self.publish_patient(session, pid, rows)
                )
                for pid, rows in self._patients.items()
            ]
            await asyncio.gather(*tasks)

            elapsed = time.time() - t0

            print(f"\n{BOLD}{'='*60}{RESET}")
            print(f"{BOLD}  TAMAMLANDI{RESET}")
            print(f"{BOLD}{'='*60}{RESET}")
            print(f"  Sure       : {elapsed:.1f}s")
            print(f"  Hasta      : {len(self._patients)}")
            print(f"  Gonderilen : {self.total_sent:,}")
            print(f"  Alert      : {self.total_alerts}")
            print(f"  Hata       : {self.total_errors}")
            print(f"  Throughput : {self.total_sent/max(elapsed,0.1):,.0f} msg/s")


# ── CLI entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Manifetch NICU Stream Publisher")
    parser.add_argument("--csv", type=str, default="data/all_data/all_vitals.csv",
                        help="all_vitals.csv yolu")
    parser.add_argument("--speed", type=float, default=50.0,
                        help="Hiz carpani (1=gercek zaman, 50=50x hizli)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Hasta basina max olcum (0=tumu)")
    parser.add_argument("--concurrency", type=int, default=50,
                        help="Ayni anda max HTTP baglantisi")
    args = parser.parse_args()

    publisher = StreamPublisher(
        csv_path=args.csv,
        speed_factor=args.speed,
        limit=args.limit,
        concurrency=args.concurrency,
    )
    publisher.load()
    asyncio.run(publisher.publish())


if __name__ == "__main__":
    main()
