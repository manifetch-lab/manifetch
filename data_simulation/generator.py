"""
Manifetch NICU — Unified Sentetik Veri Üretici v6
==================================================
v5'ten farklar:
  - Örnekleme hızları gerçek bedside monitör formatına getirildi:
      HR, SpO2 : 1 Hz (saniyede 1 değer)
      RR       : 0.5 Hz (2 saniyede 1 değer)
      ECG      : 250 Hz — ayrı dosyada (all_vitals.csv'ye dahil değil)
  - Tüm durum makineleri, literatür değerleri ve kombinasyon mantığı korundu.
  - Hastalık deltaları artık saniye bazında hesaplanıyor — daha gerçekçi.

Korunanlar (v5'ten aynı):
  - Sepsis: PRODROME → ACUTE → RECOVERY (PMC11798831, PMC8316489, PMC10314957)
  - Apnea: GA/PNA/PMA bazlı durum makinesi (PMC3158333, PMC4422349)
  - Cardiac: episodik SVT/bradyarrhythmia/AV blok (Brugada 2013, PALS, PMC3733095)
  - 1-2-3 hastalık kombinasyonları, GA kısıtları
"""

import argparse
import csv
import json
import os
import uuid
import numpy as np
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# GA GRUPLARI VE BASELINE
# ─────────────────────────────────────────────────────────────────────────────

GA_BASELINE = {
    (24, 29): {
        "hr_mean": 153, "hr_std": 15, "hr_min": 120, "hr_max": 177,
        "rr_mean": 52,  "rr_std": 10, "rr_min": 30,  "rr_max": 75,
        "spo2_mean": 93.0, "spo2_std": 3.0, "spo2_min": 88, "spo2_max": 98,
        "ecg_mean": 0.85, "ecg_std": 0.12,
    },
    (29, 33): {
        "hr_mean": 149, "hr_std": 16, "hr_min": 122, "hr_max": 175,
        "rr_mean": 48,  "rr_std": 10, "rr_min": 30,  "rr_max": 70,
        "spo2_mean": 93.5, "spo2_std": 2.8, "spo2_min": 89, "spo2_max": 98,
        "ecg_mean": 0.90, "ecg_std": 0.12,
    },
    (33, 37): {
        "hr_mean": 145, "hr_std": 15, "hr_min": 115, "hr_max": 172,
        "rr_mean": 46,  "rr_std":  9, "rr_min": 30,  "rr_max": 68,
        "spo2_mean": 94.0, "spo2_std": 2.5, "spo2_min": 90, "spo2_max": 99,
        "ecg_mean": 0.95, "ecg_std": 0.11,
    },
    (37, 43): {
        "hr_mean": 130, "hr_std": 20, "hr_min": 100, "hr_max": 160,
        "rr_mean": 44,  "rr_std":  8, "rr_min": 30,  "rr_max": 65,
        "spo2_mean": 97.0, "spo2_std": 2.0, "spo2_min": 92, "spo2_max": 100,
        "ecg_mean": 1.00, "ecg_std": 0.10,
    },
}

DISEASE_GA_LIMITS = {
    "sepsis":  (24, 42),
    "apnea":   (24, 36),
    "cardiac": (24, 42),
}

CARDIAC_TYPES = ["svt", "bradyarrhythmia", "av_block", "fluctuating"]

# Örnekleme hızları
HR_HZ   = 1      # 1 Hz
SPO2_HZ = 1      # 1 Hz
RR_HZ   = 0.5    # 0.5 Hz (2 sn'de 1)
ECG_HZ  = 25     # 25 Hz — ayrı dosya (arkadaşın formatıyla aynı)

def get_baseline(ga_weeks):
    for (lo, hi), profile in GA_BASELINE.items():
        if lo <= ga_weeks < hi:
            return profile
    return list(GA_BASELINE.values())[-1]

def compute_pma(ga_weeks, pna_days):
    return round(ga_weeks + pna_days / 7, 2)

def clamp(val, lo, hi):
    return float(max(lo, min(hi, val)))

def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return a + t * (b - a)

# ─────────────────────────────────────────────────────────────────────────────
# SEPSİS DURUM MAKİNESİ — saniye bazlı
# ─────────────────────────────────────────────────────────────────────────────

def build_sepsis_schedule(onset_sec, duration_sec, baseline, rng):
    """
    Sepsis 3 fazda gelişir (v5 ile aynı mantık, saniye bazlı):
      PRODROME (~6 saat = 21600 sn)
      ACUTE    (~24 saat = 86400 sn)
      RECOVERY
    ABD epizodları: her saniye için olasılık hesaplanır.
    Kaynak: PMC11798831, PMC8316489, PMC10314957
    """
    prodrome_dur = min(21600, int((duration_sec - onset_sec) * 0.25))
    acute_dur    = min(86400, int((duration_sec - onset_sec) * 0.50))
    recovery_dur = (duration_sec - onset_sec) - prodrome_dur - acute_dur

    # ABD olasılığı saniyeye çevrildi (dakikada 0.04 → saniyede 0.04/60)
    abd_prob_prodrome = 0.04 / 60
    abd_prob_acute    = 0.08 / 60
    abd_dur_range     = (120, 300)  # saniye (2-5 dakika)

    in_abd = False; abd_elapsed = 0; abd_duration = 0
    schedule = {}

    for s in range(onset_sec, duration_sec):
        elapsed = s - onset_sec
        if elapsed < prodrome_dur:
            phase = "PRODROME"; phase_t = elapsed / max(prodrome_dur, 1)
            abd_prob = abd_prob_prodrome
        elif elapsed < prodrome_dur + acute_dur:
            phase = "ACUTE"; phase_t = (elapsed - prodrome_dur) / max(acute_dur, 1)
            abd_prob = abd_prob_acute
        else:
            phase = "RECOVERY"; phase_t = (elapsed - prodrome_dur - acute_dur) / max(recovery_dur, 1)
            abd_prob = abd_prob_prodrome * (1 - phase_t)

        if not in_abd and rng.random() < abd_prob:
            in_abd = True
            abd_duration = int(rng.integers(abd_dur_range[0], abd_dur_range[1]))
            abd_elapsed = 0

        is_abd = False
        if in_abd:
            is_abd = True; abd_elapsed += 1
            if abd_elapsed >= abd_duration: in_abd = False

        schedule[s] = {"phase": phase, "phase_t": phase_t, "is_abd": is_abd}

    return schedule


def sepsis_delta(schedule, sec, baseline, rng, ga_weeks, pna_days):
    """
    GA ve PNA bazlı sepsis yanıtı.
    Erken prematüre: daha belirgin taşikardi, daha derin SpO2 düşüşü (PMC8316489, PMC11798831)
    PNA 1-7: daha instabil (yüksek gürültü) — PMC10314957
    """
    info = schedule.get(sec)
    if info is None:
        return {"hr": 0, "rr": 0, "spo2": 0, "ecg": 0, "label": 0}

    # GA şiddet faktörü — erken prematüre daha güçlü yanıt
    if ga_weeks < 28:   ga_f = 1.6
    elif ga_weeks < 32: ga_f = 1.3
    elif ga_weeks < 36: ga_f = 1.1
    else:               ga_f = 1.0

    # PNA instabilite faktörü — ilk hafta daha değişken
    if pna_days <= 7:    pna_noise = 1.6
    elif pna_days <= 14: pna_noise = 1.2
    else:                pna_noise = 1.0

    phase = info["phase"]; t = info["phase_t"]; is_abd = info["is_abd"]

    if phase == "PRODROME":
        hr_d   = lerp(0, 5  * ga_f, t) + rng.normal(0, 2   * pna_noise)
        rr_d   = lerp(0, 5  * ga_f, t) + rng.normal(0, 1.5 * pna_noise)
        spo2_d = lerp(0, -2 * ga_f, t) + rng.normal(0, 0.3 * pna_noise)
        ecg_d  = -0.02 * t
    elif phase == "ACUTE":
        hr_d   = lerp(5  * ga_f, 15 * ga_f,  t) + rng.normal(0, 3   * pna_noise)
        rr_d   = lerp(5  * ga_f, 20 * ga_f,  t) + rng.normal(0, 2   * pna_noise)
        spo2_d = lerp(-2 * ga_f, -10 * ga_f, t) + rng.normal(0, 0.8 * pna_noise)
        ecg_d  = lerp(-0.02, -0.15 * ga_f, t)   + rng.normal(0, 0.02)
    else:  # RECOVERY
        hr_d   = lerp(15 * ga_f, 0, t) + rng.normal(0, 2   * pna_noise)
        rr_d   = lerp(20 * ga_f, 0, t) + rng.normal(0, 1.5 * pna_noise)
        spo2_d = lerp(-10 * ga_f, 0, t)+ rng.normal(0, 0.6 * pna_noise)
        ecg_d  = lerp(-0.15 * ga_f, 0, t)

    if is_abd:
        abd_f  = ga_f
        hr_d   -= rng.uniform(15 * abd_f, 35 * abd_f)
        spo2_d -= rng.uniform(5  * abd_f, 12 * abd_f)
        rr_d   -= rng.uniform(10 * abd_f, 25 * abd_f)

    return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 1}


# ─────────────────────────────────────────────────────────────────────────────
# APNEA DURUM MAKİNESİ — saniye bazlı
# ─────────────────────────────────────────────────────────────────────────────

def apnea_severity(ga_weeks, pna_days, pma_weeks):
    if pma_weeks >= 44: return 0.0
    pma_factor = 1.0 if pma_weeks < 36 else 1.0 - (pma_weeks - 36) / 8.0
    ga_factor  = 1.0 if ga_weeks < 28 else (0.75 if ga_weeks < 32 else 0.50)
    pna_factor = 1.0 if 14 <= pna_days <= 28 else (0.6 if pna_days < 7 else 0.8)
    return pma_factor * ga_factor * pna_factor


def build_apnea_schedule(ga_weeks, pna_days, pma_weeks, onset_sec, duration_sec, rng):
    """
    Apnea durum makinesi saniye bazlı — PRE_APNEA eklenmiştir.
    Apne öncesi 2-5 dk: periodic breathing (HR değişkenliği artışı, düzensiz RR).
    Kaynak: PMC3158333, PMC4422349, PMC3387856
    """
    severity = apnea_severity(ga_weeks, pna_days, pma_weeks)
    if severity == 0.0: return {}

    if ga_weeks < 28:
        apnea_prob   = 0.18 * severity / 60
        dur_range    = (20, 60)
        recovery_sec = 300
        desat_target = rng.uniform(62, 72)
        brady_floor  = 0.60
        rr_min_apnea = 0.0
    elif ga_weeks < 32:
        apnea_prob   = 0.12 * severity / 60
        dur_range    = (20, 45)
        recovery_sec = 240
        desat_target = rng.uniform(70, 78)
        brady_floor  = 0.65
        rr_min_apnea = 2.0
    else:
        apnea_prob   = 0.06 * severity / 60
        dur_range    = (20, 35)
        recovery_sec = 180
        desat_target = rng.uniform(76, 83)
        brady_floor  = 0.70
        rr_min_apnea = 5.0

    SPO2_DELAY_SEC = 15

    # ── Geçiş 1: tüm apne başlangıç zamanlarını topla ────────
    events = []
    in_apnea = False; apnea_elapsed = 0; apnea_duration = 0; recovery_left = 0
    for s in range(onset_sec, duration_sec):
        if not in_apnea and recovery_left <= 0:
            if rng.random() < apnea_prob:
                in_apnea = True
                apnea_duration = int(rng.integers(dur_range[0], dur_range[1]))
                apnea_elapsed  = 0
                events.append((s, apnea_duration))
        if in_apnea:
            apnea_elapsed += 1
            if apnea_elapsed >= apnea_duration:
                in_apnea = False; recovery_left = recovery_sec
        elif recovery_left > 0:
            recovery_left -= 1

    # ── Geçiş 2: schedule'ı doldur ───────────────────────────
    schedule = {}
    for apnea_start, apnea_dur in events:
        # PRE_APNEA: 2-5 dk önce (periodic breathing / artan HR variabilitesi)
        pre_dur   = int(rng.integers(120, 300))
        pre_start = max(onset_sec, apnea_start - pre_dur)
        for s in range(pre_start, apnea_start):
            if s not in schedule:
                t = (s - pre_start) / max(pre_dur, 1)
                schedule[s] = {
                    "state": "PRE_APNEA", "phase_t": t,
                    "brady_floor": brady_floor, "rr_min": rr_min_apnea,
                }

        # APNEA
        for elapsed in range(apnea_dur):
            s = apnea_start + elapsed
            if s >= duration_sec: break
            schedule[s] = {
                "state": "APNEA", "elapsed": elapsed,
                "duration": apnea_dur, "desat_target": desat_target,
                "brady_floor": brady_floor, "rr_min": rr_min_apnea,
                "recovery_sec": recovery_sec, "spo2_delay": SPO2_DELAY_SEC,
            }

        # RECOVERY
        for step in range(recovery_sec):
            s = apnea_start + apnea_dur + step
            if s >= duration_sec: break
            if s not in schedule:
                schedule[s] = {
                    "state": "RECOVERY",
                    "recovery_step": step,
                    "recovery_sec": recovery_sec,
                    "desat_target": desat_target,
                    "brady_floor": brady_floor, "rr_min": rr_min_apnea,
                }

    return schedule


def apnea_delta(schedule, sec, baseline, rng):
    info = schedule.get(sec)
    if info is None:
        return {"hr": 0, "rr": 0, "spo2": 0, "ecg": 0, "label": 0}

    hr_base   = baseline["hr_mean"]
    spo2_base = baseline["spo2_mean"]
    rr_base   = baseline["rr_mean"]

    if info["state"] == "PRE_APNEA":
        # Periodic breathing: artan HR variabilitesi, düzensiz RR, hafif SpO2 dalgalanması
        # Kaynak: PMC4422349 — apne öncesi periodik solunum paterni
        t = info["phase_t"]
        hr_noise_scale = lerp(1.0, 2.5, t)   # giderek artan variabilite
        rr_noise_scale = lerp(1.0, 3.0, t)   # RR giderek daha düzensiz
        hr_d   = lerp(0, 6, t) + rng.normal(0, baseline["hr_std"] * hr_noise_scale)
        rr_d   = rng.normal(0, baseline["rr_std"] * rr_noise_scale)
        spo2_d = rng.normal(0, baseline["spo2_std"] * lerp(1.0, 1.8, t))
        ecg_d  = rng.normal(0, 0.02)
        return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 0}

    if info["state"] == "APNEA":
        elapsed = info["elapsed"]; duration = info["duration"]
        t = elapsed / max(duration, 1)
        brady_floor  = hr_base * info["brady_floor"]
        desat_target = info["desat_target"]
        rr_min       = info["rr_min"]
        spo2_delay   = info["spo2_delay"]

        # RR hemen düşer
        rr_d = (rr_base * (1 - t) + rr_min * t) - rr_base + rng.normal(0, 0.3)

        # SpO2: ~15 sn gecikme (PMC3158333)
        if elapsed < spo2_delay:
            spo2_d = rng.normal(0, 0.2)
        else:
            t2 = (elapsed - spo2_delay) / max(duration - spo2_delay, 1)
            spo2_d = (spo2_base * (1-t2) + desat_target * t2) - spo2_base + rng.normal(0, 0.5)

        # HR: taşikardi → bradikardi
        current_spo2 = spo2_base + spo2_d
        if current_spo2 >= 80:
            hr_target = hr_base + 20 * min(t / 0.3, 1.0)
        else:
            brady_t = clamp((80 - current_spo2) / 20, 0, 1)
            hr_target = brady_floor + (hr_base + 20 - brady_floor) * (1 - brady_t)
        hr_d = hr_target - hr_base + rng.normal(0, 2)
        ecg_d = -0.15 * t + rng.normal(0, 0.02)

        return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 1}

    else:  # RECOVERY
        step = info["recovery_step"]; dur = info["recovery_sec"]
        t = (step + 1) / dur
        brady_floor  = hr_base * info["brady_floor"]
        desat_target = info["desat_target"]
        rr_min       = info["rr_min"]
        return {
            "hr":    (brady_floor - hr_base) * (1 - clamp(t*0.8, 0, 1)) + rng.normal(0, 2),
            "rr":    (rr_min - rr_base) * (1 - t) + rng.normal(0, 0.8),
            "spo2":  (desat_target - spo2_base) * (1 - clamp(t*1.5, 0, 1)) + rng.normal(0, 0.5),
            "ecg":   -0.10 * (1 - t) + rng.normal(0, 0.01),
            "label": 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# KARDİYAK ANOMALİ DURUM MAKİNESİ — saniye bazlı
# ─────────────────────────────────────────────────────────────────────────────

def build_cardiac_schedule(onset_sec, duration_sec, cardiac_type, rng, ga_weeks):
    """
    Episodik aritmi — saniye bazlı, GA bazlı şiddet.
    Erken prematüre: SVT daha hızlı, bradikardi daha derin (Brugada 2013, PALS, PMC3733095)
    """
    # GA bazlı SVT ve brady şiddet parametreleri
    if ga_weeks < 28:
        svt_peak_range   = (90, 140)   # çok yüksek SVT HR delta
        brady_peak_range = (50, 85)    # çok derin bradikardi delta
        av_peak_range    = (25, 45)
    elif ga_weeks < 32:
        svt_peak_range   = (80, 125)
        brady_peak_range = (43, 72)
        av_peak_range    = (22, 38)
    elif ga_weeks < 36:
        svt_peak_range   = (72, 115)
        brady_peak_range = (38, 65)
        av_peak_range    = (18, 32)
    else:
        svt_peak_range   = (65, 105)
        brady_peak_range = (32, 58)
        av_peak_range    = (15, 28)

    if cardiac_type == "svt":
        interval_range = (2700, 10800)
        dur_range      = (180, 1500)
    elif cardiac_type == "bradyarrhythmia":
        interval_range = (1800, 7200)
        dur_range      = (120, 900)
    elif cardiac_type == "av_block":
        interval_range = (3600, 14400)
        dur_range      = (300, 1800)
    else:  # fluctuating
        interval_range = (1800, 5400)
        dur_range      = (120, 1200)

    schedule = {}
    s = onset_sec

    while s < duration_sec:
        wait = int(rng.integers(interval_range[0], interval_range[1]))
        s += wait
        if s >= duration_sec: break

        ep_dur       = int(rng.integers(dur_range[0], dur_range[1]))
        onset_dur    = max(1, ep_dur // 5)
        peak_dur     = max(1, ep_dur // 2)
        recovery_dur = max(1, ep_dur - onset_dur - peak_dur)

        ep_subtype = str(rng.choice(["svt", "bradyarrhythmia"])) if cardiac_type == "fluctuating" else cardiac_type

        if ep_subtype == "svt":
            peak_hr   =  float(rng.uniform(*svt_peak_range))
            peak_spo2 = -float(rng.uniform(2, 8))
            peak_ecg  = -float(rng.uniform(0.30, 0.50))
            peak_rr   =  float(rng.uniform(5, 15))
        elif ep_subtype == "bradyarrhythmia":
            peak_hr   = -float(rng.uniform(*brady_peak_range))
            peak_spo2 = -float(rng.uniform(3, 12))
            peak_ecg  = -float(rng.uniform(0.20, 0.40))
            peak_rr   =  float(rng.uniform(-5, 5))
        else:  # av_block
            peak_hr   = -float(rng.uniform(*av_peak_range))
            peak_spo2 = -float(rng.uniform(1, 5))
            peak_ecg  = -float(rng.uniform(0.15, 0.25))
            peak_rr   =  float(rng.uniform(-3, 3))

        # PRE_EPISODE: 5-15 dk önce (hafif HR kayması + artan variabilite)
        # SVT öncesi: hafif taşikardi + HRV artışı (Brugada 2013)
        # Brady öncesi: hafif bradikardi + düzensizleşme
        pre_dur   = int(rng.integers(300, 900))
        pre_start = max(onset_sec, s - pre_dur)
        pre_hr    = lerp(0, peak_hr * 0.15, 1.0)  # epizodun %15'i kadar öncü kayma
        for j in range(pre_start, s):
            if j not in schedule:
                t = (j - pre_start) / max(s - pre_start, 1)
                schedule[j] = {
                    "phase": "PRE_EPISODE", "phase_t": t, "subtype": ep_subtype,
                    "pre_hr": pre_hr,
                    "peak_hr": peak_hr, "peak_spo2": peak_spo2,
                    "peak_ecg": peak_ecg, "peak_rr": peak_rr,
                }

        # Epizod fazları
        for j in range(ep_dur):
            t_s = s + j
            if t_s >= duration_sec: break
            if j < onset_dur:
                phase = "ONSET"; phase_t = j / max(onset_dur, 1)
            elif j < onset_dur + peak_dur:
                phase = "PEAK"; phase_t = (j - onset_dur) / max(peak_dur, 1)
            else:
                phase = "RECOVERY"; phase_t = (j - onset_dur - peak_dur) / max(recovery_dur, 1)

            schedule[t_s] = {
                "phase": phase, "phase_t": phase_t, "subtype": ep_subtype,
                "peak_hr": peak_hr, "peak_spo2": peak_spo2,
                "peak_ecg": peak_ecg, "peak_rr": peak_rr,
            }

        s += ep_dur

    return schedule


def cardiac_delta(schedule, sec, rng):
    info = schedule.get(sec)
    if info is None:
        return {"hr": 0, "rr": 0, "spo2": 0, "ecg": 0, "label": 0}

    phase = info["phase"]; t = info["phase_t"]
    peak_hr = info["peak_hr"]; peak_spo2 = info["peak_spo2"]
    peak_ecg = info["peak_ecg"]; peak_rr = info["peak_rr"]

    if phase == "PRE_EPISODE":
        # Hafif öncü HR kayması + artan variabilite (Brugada 2013)
        pre_hr = info["pre_hr"]
        hr_noise_scale = lerp(1.0, 2.0, t)
        hr_d   = lerp(0, pre_hr, t) + rng.normal(0, 3 * hr_noise_scale)
        rr_d   = rng.normal(0, 1.5 * lerp(1.0, 2.0, t))
        spo2_d = rng.normal(0, 0.3)
        ecg_d  = lerp(0, peak_ecg * 0.1, t)
        return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 0}

    if phase == "ONSET":
        hr_d   = lerp(0, peak_hr,   t) + rng.normal(0, 3)
        spo2_d = lerp(0, peak_spo2, t) + rng.normal(0, 0.4)
        ecg_d  = lerp(0, peak_ecg,  t)
        rr_d   = lerp(0, peak_rr,   t) + rng.normal(0, 1.5)
    elif phase == "PEAK":
        hr_d   = peak_hr   + rng.normal(0, 5)
        spo2_d = peak_spo2 + rng.normal(0, 0.8)
        ecg_d  = peak_ecg  + rng.normal(0, 0.03)
        rr_d   = peak_rr   + rng.normal(0, 1.5)
    else:
        hr_d   = lerp(peak_hr,   0, t) + rng.normal(0, 4)
        spo2_d = lerp(peak_spo2, 0, t) + rng.normal(0, 0.6)
        ecg_d  = lerp(peak_ecg,  0, t)
        rr_d   = lerp(peak_rr,   0, t) + rng.normal(0, 1.5)

    return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 1}


# ─────────────────────────────────────────────────────────────────────────────
# ECG WAVEFORM — 25 Hz, ayrı dosya
# ─────────────────────────────────────────────────────────────────────────────

def build_ecg_waveform(duration_sec, baseline, cardiac_schedule, apnea_schedule,
                        sepsis_schedule, ga_weeks, seed):
    """
    25 Hz ECG waveform uretir — PQRST morfolojisi gorunur.
    Bradikardi/tasikardi RR araliklarinda yansir.
    """
    rng = np.random.default_rng(seed + 777777)
    FS = ECG_HZ  # 25 Hz
    n_samples = duration_sec * FS
    ecg = np.zeros(n_samples)

    hr_base  = baseline["hr_mean"]
    amp_base = baseline["ecg_mean"]

    # Saniye bazli HR dizisi (schedule'lardan vektorel)
    hr_per_sec = np.full(duration_sec, hr_base) + rng.normal(0, baseline["hr_std"] * 0.3, duration_sec)

    for s in range(duration_sec):
        info_c = cardiac_schedule.get(s)
        if info_c:
            ph = info_c["phase"]; t = info_c["phase_t"]; pk = info_c["peak_hr"]
            hr_per_sec[s] += pk if ph == "PEAK" else (lerp(0, pk, t) if ph == "ONSET" else lerp(pk, 0, t))
        info_a = apnea_schedule.get(s)
        if info_a and info_a["state"] == "APNEA":
            brady_floor = hr_base * info_a["brady_floor"]
            t = info_a["elapsed"] / max(info_a["duration"], 1)
            if t > 0.3:
                hr_per_sec[s] = brady_floor + (hr_per_sec[s] - brady_floor) * (1 - min((t-0.3)/0.7, 1))

    hr_per_sec = np.clip(hr_per_sec, 50, 280)

    # PQRST sablon (25 Hz icin ayarli)
    template_len = int(FS * 0.5)  # 12-13 sample
    t = np.linspace(0, 1, template_len)
    # 25 Hz'de 12 sample/beat — Q ve S ayırt edilemez, P + R + T yeterli
    # R piki: std=0.06 (~1.5 sample), P: std=0.08, T: std=0.12
    template_base = amp_base * (
        0.08 * np.exp(-((t-0.15)**2)/(2*0.08**2)) +   # P dalgası
        1.00 * np.exp(-((t-0.35)**2)/(2*0.06**2)) +   # R piki (QRS kompleksi)
        0.10 * np.exp(-((t-0.65)**2)/(2*0.12**2))     # T dalgası
    )

    beat_idx = 0
    while beat_idx < n_samples:
        sec = min(beat_idx // FS, duration_sec - 1)
        hr  = hr_per_sec[sec]
        rr  = max(2, int(60.0 / hr * FS))

        # Amplitud degisimi
        amp_factor = 1.0
        info_c = cardiac_schedule.get(sec)
        info_a = apnea_schedule.get(sec)
        if info_c:
            amp_factor += info_c["peak_ecg"] / amp_base * (info_c["phase_t"] if info_c["phase"] != "PEAK" else 1.0)
        if info_a and info_a["state"] == "APNEA":
            t = info_a["elapsed"] / max(info_a["duration"], 1)
            amp_factor -= 0.15 * t
        amp_factor = max(0.1, amp_factor)

        template = template_base * amp_factor
        jitter = int(rng.normal(0, rr * 0.02))
        start  = beat_idx + jitter
        seg    = min(template_len, n_samples - start)
        if start >= 0 and seg > 0:
            ecg[start:start+seg] += template[:seg]
        beat_idx += rr

    # Baseline wander + gurultu
    t_arr = np.arange(n_samples) / FS
    ecg  += 0.05 * amp_base * np.sin(2 * np.pi * 0.1 * t_arr)
    ecg  += rng.normal(0, 0.015 * amp_base, n_samples)

    return np.round(ecg, 4)

def generate_patient(patient_id, ga_weeks, pna_days, diseases,
                     cardiac_type, duration_hours, start_time, seed, output_dir):
    baseline     = get_baseline(ga_weeks)
    pma_weeks    = compute_pma(ga_weeks, pna_days)
    duration_sec = int(duration_hours * 3600)
    sched_rng    = np.random.default_rng(seed + 99999)

    # Onset saniyeye çevir
    onset_map = {d: int(v * 60) for d, v in diseases.items()}

    # Schedule'ları üret
    sep_sched  = build_sepsis_schedule( onset_map.get("sepsis",  0), duration_sec, baseline, sched_rng) if "sepsis"  in diseases else {}
    apn_sched  = build_apnea_schedule(  ga_weeks, pna_days, pma_weeks, onset_map.get("apnea", 0), duration_sec, sched_rng) if "apnea"   in diseases else {}
    card_sched = build_cardiac_schedule(onset_map.get("cardiac", 0), duration_sec, cardiac_type, sched_rng, ga_weeks) if "cardiac" in diseases else {}

    # PNA bazlı baseline instabilite — ilk 7 gün daha değişken (PMC10314957)
    if pna_days <= 7:    baseline_noise_f = 1.5
    elif pna_days <= 14: baseline_noise_f = 1.2
    else:                baseline_noise_f = 1.0

    # ── HR ve SpO2: 1 Hz ──────────────────────────────────────────────────────
    hr_rows   = []
    spo2_rows = []
    rr_rows   = []
    for s in range(duration_sec):
        rng_s = np.random.default_rng(seed + s * 7)
        ts    = (start_time + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_sec = round(float(s), 3)

        # Baseline — PNA instabilite faktörü uygulanır
        hr   = baseline["hr_mean"]   + rng_s.normal(0, baseline["hr_std"]   * 0.4 * baseline_noise_f)
        spo2 = baseline["spo2_mean"] + rng_s.normal(0, baseline["spo2_std"] * 0.4 * baseline_noise_f)

        label_s = 0; label_a = 0; label_c = 0

        if "sepsis" in diseases:
            d = sepsis_delta(sep_sched, s, baseline, rng_s, ga_weeks, pna_days)
            hr += d["hr"]; spo2 += d["spo2"]; label_s = d["label"]

        if "apnea" in diseases:
            d = apnea_delta(apn_sched, s, baseline, rng_s)
            hr += d["hr"]; spo2 += d["spo2"]; label_a = d["label"]

        if "cardiac" in diseases:
            d = cardiac_delta(card_sched, s, rng_s)
            hr += d["hr"]; spo2 += d["spo2"]; label_c = d["label"]

        # ── Concurrent etkileşimler ──────────────────────────────────────
        if "sepsis" in diseases and "apnea" in diseases:
            sep_info = sep_sched.get(s)
            apn_info = apn_sched.get(s)
            if sep_info and apn_info:
                sep_active = sep_info.get("phase") in ("PRODROME", "ACUTE")
                apn_state  = apn_info.get("state", "")
                if apn_state == "APNEA" and sep_active:
                    # Bileşik hipoksi: SpO2 daha derin düşer (PMC8316489)
                    spo2 -= rng_s.uniform(2, 5)
                    # Sepsis taşikardisi bradıkardıyi kısmen maskeler
                    hr   += rng_s.uniform(5, 12)
                elif apn_state == "PRE_APNEA" and sep_active:
                    # PRE_APNEA prodromunun HR sinyali sepsis taşikardisi ile örtüşür —
                    # ama RR irregular paterni daha belirgin hale gelir (period. breathing)
                    rr_boost = rng_s.choice([-6.0, -5.0, 5.0, 6.0]) * rng_s.random()
                    # rr değişkeni RR döngüsünde hesaplanır; burada HR sinyalini baskıla
                    hr -= rng_s.uniform(0, 4)   # PRE_APNEA HR artışı kısmen bastırılır

        label_h = 1 if not any([label_s, label_a, label_c]) else 0

        hr   = round(clamp(hr,   50, 280), 1)
        spo2 = round(clamp(spo2, 65, 100), 1)
        is_valid_spo2 = spo2 >= baseline["spo2_min"] - 5

        common = {
            "measurementId":       str(uuid.uuid4()),
            "patientId":           patient_id,
            "timestamp":           ts,
            "gestationalAgeWeeks": ga_weeks,
            "postnatalAgeDays":    pna_days,
            "pma_weeks":           pma_weeks,
            "label_sepsis":        label_s,
            "label_apnea":         label_a,
            "label_cardiac":       label_c,
            "label_healthy":       label_h,
        }

        hr_rows.append({**common, "timestamp_sec": ts_sec,
                        "signalType": "HEART_RATE", "value": hr,
                        "unit": "BPM", "isValid": True})
        spo2_rows.append({**common, "timestamp_sec": ts_sec,
                          "signalType": "SPO2", "value": spo2,
                          "unit": "%", "isValid": is_valid_spo2})

    # ── RR: 0.5 Hz (her 2 saniyede bir) ──────────────────────────────────────
    for s in range(0, duration_sec, 2):
        rng_s = np.random.default_rng(seed + s * 11)
        ts    = (start_time + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_sec = round(float(s), 3)

        rr = baseline["rr_mean"] + rng_s.normal(0, baseline["rr_std"] * 0.4 * baseline_noise_f)

        label_s = 0; label_a = 0; label_c = 0

        if "sepsis" in diseases:
            d = sepsis_delta(sep_sched, s, baseline, rng_s, ga_weeks, pna_days)
            rr += d["rr"]; label_s = d["label"]

        if "apnea" in diseases:
            d = apnea_delta(apn_sched, s, baseline, rng_s)
            rr += d["rr"]; label_a = d["label"]

        if "cardiac" in diseases:
            d = cardiac_delta(card_sched, s, rng_s)
            rr += d["rr"]; label_c = d["label"]

        # ── Concurrent etkileşimler (RR) ────────────────────────────────
        if "sepsis" in diseases and "apnea" in diseases:
            sep_info = sep_sched.get(s)
            apn_info = apn_sched.get(s)
            if sep_info and apn_info:
                sep_active = sep_info.get("phase") in ("PRODROME", "ACUTE")
                apn_state  = apn_info.get("state", "")
                if apn_state == "PRE_APNEA" and sep_active:
                    # Periodik solunum paterni sepsis taşipnesinin üstünde daha belirgin
                    rr_boost = rng_s.choice([-6.0, -5.0, 5.0, 6.0]) * rng_s.random()
                    rr += rr_boost

        label_h = 1 if not any([label_s, label_a, label_c]) else 0
        rr = round(clamp(rr, 0, 90), 1)

        common = {
            "measurementId":       str(uuid.uuid4()),
            "patientId":           patient_id,
            "timestamp":           ts,
            "gestationalAgeWeeks": ga_weeks,
            "postnatalAgeDays":    pna_days,
            "pma_weeks":           pma_weeks,
            "label_sepsis":        label_s,
            "label_apnea":         label_a,
            "label_cardiac":       label_c,
            "label_healthy":       label_h,
        }
        rr_rows.append({**common, "timestamp_sec": ts_sec,
                        "signalType": "RESP_RATE", "value": rr,
                        "unit": "breaths/min", "isValid": True})



    # ── ECG: 25 Hz — ayrı dosya, pandas ile hızlı yazım ─────────────────────
    # 25 Hz: PQRST dalgaları görünür, dosya boyutu makul
    # timestamp_sec: admission_time başlangıcından saniye cinsinden offset
    ecg_signal = build_ecg_waveform(duration_sec, baseline, card_sched, apn_sched,
                                     sep_sched, ga_weeks, seed)

    import pandas as pd
    n_ecg = len(ecg_signal)
    ts_secs = np.round(np.arange(n_ecg) / ECG_HZ, 4)

    ecg_df = pd.DataFrame({
        "timestamp_sec": ts_secs,
        "ecg_mv":        ecg_signal,
        "signal_type":   "ECG",
        "unit":          "mV",
        "patient_id":    patient_id,
    })
    ecg_path = os.path.join(output_dir, f"ecg_{patient_id[:8]}.csv")
    ecg_df.to_csv(ecg_path, index=False)
    return hr_rows, spo2_rows, rr_rows


# ─────────────────────────────────────────────────────────────────────────────
# HASTA TANIMLAYICI
# ─────────────────────────────────────────────────────────────────────────────

def assign_diseases(ga_weeks, is_healthy, duration_min, rng, forced_combo=None):
    """
    GA'ya göre hastalık olasılığı — hard cutoff yerine gradient.
    forced_combo: None veya liste, örn. ["apnea","sepsis"] — dağılım kotası için.
    Kaynak: PMC3158333 (apnea), PMC8316489 (sepsis), Brugada 2013 (cardiac)
    """
    if is_healthy:
        return {}, None

    if forced_combo is not None:
        selected = list(forced_combo)
    else:
        # Her hastalık için GA bazlı olasılık ağırlığı (0-1 arası)
        def apnea_weight(ga):
            if ga < 28:  return 0.85
            if ga < 32:  return 0.50
            if ga < 36:  return 0.25
            if ga < 40:  return 0.08
            return 0.02

        def sepsis_weight(ga):
            if ga < 28:  return 0.70
            if ga < 32:  return 0.65
            if ga < 36:  return 0.60
            return 0.55

        def cardiac_weight(ga):
            return 0.50

        weights = {
            "apnea":   apnea_weight(ga_weeks),
            "sepsis":  sepsis_weight(ga_weeks),
            "cardiac": cardiac_weight(ga_weeks),
        }

        selected = [d for d, w in weights.items() if rng.random() < w]

        if not selected:
            all_d = list(weights.keys())
            all_w = np.array([weights[d] for d in all_d])
            all_w = all_w / all_w.sum()
            selected = [str(rng.choice(all_d, p=all_w))]

    diseases = {}
    for disease in selected:
        onset = int(rng.uniform(0, duration_min * 0.20))
        diseases[disease] = onset

    cardiac_type = str(rng.choice(CARDIAC_TYPES)) if "cardiac" in diseases else None
    return diseases, cardiac_type


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_patients",     type=int,   default=10)
    parser.add_argument("--duration_hours", type=float, default=48)
    parser.add_argument("--healthy_ratio",  type=float, default=0.30)
    parser.add_argument("--output_dir",     type=str,   default="data/data_all")
    parser.add_argument("--seed",           type=int,   default=42)
    parser.add_argument("--no_ecg",         action="store_true",
                        help="ECG waveform üretme (büyük dosya, test için)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    rng          = np.random.default_rng(args.seed)
    duration_min = int(args.duration_hours * 60)
    n_healthy    = int(args.n_patients * args.healthy_ratio)
    start_time   = datetime(2024, 1, 10, 8, 30, 0)

    print("=" * 60)
    print("Manifetch NICU — Unified Sentetik Veri Üretici v6")
    print(f"Örnekleme: HR/SpO2=1Hz, RR=0.5Hz, ECG=25Hz")
    print("=" * 60)
    print(f"Hasta sayısı   : {args.n_patients}")
    print(f"Süre           : {args.duration_hours} saat")
    print(f"Sağlıklı oran  : {args.healthy_ratio:.0%}")
    print()

    # ── Dağılım kotası — train kalitesi için dengeli kombinasyonlar ───────────
    # Toplam hasta: n_patients, sağlıklı: n_healthy, hasta: n_sick
    # Kota: her kombinasyon için minimum sayı garantisi, kalanlar olasılıksal
    n_sick = args.n_patients - n_healthy
    combos = [
        ["apnea"],
        ["cardiac"],
        ["sepsis"],
        ["apnea", "cardiac"],
        ["apnea", "sepsis"],      # ← en zor concurrent, 2x
        ["apnea", "sepsis"],
        ["cardiac", "sepsis"],
        ["apnea", "cardiac", "sepsis"],
    ]
    # n_sick hastayla kota listesi: kotalar önce gelir, kalanlar olasılıksal
    quota_list = []
    if n_sick >= len(combos):
        quota_list = combos.copy()
        rng.shuffle(quota_list)
    forced_iter = iter(quota_list)

    stats = {}; all_hr = []; all_spo2 = []; all_rr = []
    metadata = []

    for i in range(args.n_patients):
        patient_id = str(uuid.uuid4())
        is_healthy = i < n_healthy
        ga_weeks   = int(rng.integers(24, 42))
        pna_days   = int(rng.integers(1, 29))
        pma_weeks  = compute_pma(ga_weeks, pna_days)
        seed_p     = args.seed * 1000 + i * 37

        forced = next(forced_iter, None) if not is_healthy else None
        diseases, cardiac_type = assign_diseases(ga_weeks, is_healthy, duration_min, rng,
                                                  forced_combo=forced)

        key = "healthy" if not diseases else (f"{list(diseases.keys())[0]}_only" if len(diseases) == 1 else "combined")
        stats[key] = stats.get(key, 0) + 1

        patient_start = start_time + timedelta(seconds=i * 13)

        print(f"  [{i+1}/{args.n_patients}] GA={ga_weeks}w PNA={pna_days}d diseases={list(diseases.keys())}...")

        hr_rows, spo2_rows, rr_rows = generate_patient(
            patient_id=patient_id, ga_weeks=ga_weeks, pna_days=pna_days,
            diseases=diseases, cardiac_type=cardiac_type,
            duration_hours=args.duration_hours,
            start_time=patient_start, seed=seed_p,
            output_dir=args.output_dir,
        )

        all_hr.extend(hr_rows)
        all_spo2.extend(spo2_rows)
        all_rr.extend(rr_rows)

        metadata.append({
            "patientId": patient_id, "gestationalAgeWeeks": ga_weeks,
            "postnatalAgeDays": pna_days, "pma_weeks": pma_weeks,
            "diseases": list(diseases.keys()), "disease_onsets_min": diseases,
            "cardiac_type": cardiac_type, "is_healthy": is_healthy,
        })

    # ── all_vitals.csv (HR + SpO2 + RR, timestamp sıralı) ────────────────────
    print("\nall_vitals.csv oluşturuluyor...")
    all_rows = all_hr + all_spo2 + all_rr
    all_rows.sort(key=lambda r: (r["timestamp"], r["patientId"]))

    fieldnames = ["measurementId","patientId","timestamp","timestamp_sec",
                  "signalType","value","unit","isValid",
                  "gestationalAgeWeeks","postnatalAgeDays","pma_weeks",
                  "label_sepsis","label_apnea","label_cardiac","label_healthy"]

    out_path = os.path.join(args.output_dir, "all_vitals.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # ── Metadata ──────────────────────────────────────────────────────────────
    meta_path = os.path.join(args.output_dir, "patients_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat() + "Z",
            "version": "v6",
            "sampling": {"HR_Hz": HR_HZ, "SpO2_Hz": SPO2_HZ, "RR_Hz": RR_HZ, "ECG_Hz": ECG_HZ},
            "n_patients": args.n_patients,
            "duration_hours": args.duration_hours,
            "healthy_ratio": args.healthy_ratio,
            "patients": metadata,
        }, f, indent=2, ensure_ascii=False)

    total = args.n_patients
    print()
    print("=" * 60)
    print("TAMAMLANDI")
    print("=" * 60)
    print(f"Toplam satır (all_vitals): {len(all_rows):,}")
    print(f"  HR  (1 Hz):   {len(all_hr):,}")
    print(f"  SpO2 (1 Hz):  {len(all_spo2):,}")
    print(f"  RR  (0.5 Hz): {len(all_rr):,}")
    print(f"ECG: her hasta için ayrı *_ecg_waveform.csv (250 Hz)")
    print()
    print("--- Hasta Dağılımı ---")
    for key in ["healthy", "sepsis_only", "apnea_only", "cardiac_only", "combined"]:
        n = stats.get(key, 0)
        print(f"  {key.replace('_',' ').title():<18}: {n:3d} ({n/total:.0%})")
    print()
    print(f"Kaydedildi: {args.output_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()