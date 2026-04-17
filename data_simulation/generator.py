import argparse
import csv
import json
import os
import uuid
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

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

# DÜZELTME: DISEASE_GA_LIMITS artık aktif olarak kullanılıyor
DISEASE_GA_LIMITS = {
    "sepsis":  (24, 42),
    "apnea":   (24, 36),   # 36 hafta üstünde apnea riski çok düşük
    "cardiac": (24, 42),
}

CARDIAC_TYPES = ["svt", "bradyarrhythmia", "av_block", "fluctuating"]

# Örnekleme hızları
HR_HZ   = 1      # 1 Hz
SPO2_HZ = 1      # 1 Hz
RR_HZ   = 0.5    # 0.5 Hz (2 sn'de 1)
ECG_HZ  = 25     # 25 Hz — ayrı dosya


# ─────────────────────────────────────────────────────────────────────────────
# LLD: ScenarioConfig sınıfı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScenarioConfig:
    """
    LLD: ScenarioConfig
    Attributes: patientId, samplingRateHz, durationSeconds, signalTypes
    """
    patient_id:       str
    duration_seconds: int
    signal_types:     list = field(default_factory=lambda: ["HEART_RATE", "SPO2", "RESP_RATE", "ECG"])
    ga_weeks:         int  = 32
    pna_days:         int  = 14
    diseases:         dict = field(default_factory=dict)
    cardiac_type:     Optional[str] = None
    seed:             int  = 42
    sampling_rate_hz: dict = field(default_factory=lambda: {
        "HEART_RATE": HR_HZ,
        "SPO2":       SPO2_HZ,
        "RESP_RATE":  RR_HZ,
        "ECG":        ECG_HZ,
    })


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────

def get_baseline(ga_weeks: int) -> dict:
    for (lo, hi), profile in GA_BASELINE.items():
        if lo <= ga_weeks < hi:
            return profile
    return list(GA_BASELINE.values())[-1]


def compute_pma(ga_weeks: int, pna_days: int) -> float:
    return round(ga_weeks + pna_days / 7, 2)


def clamp(val, lo, hi) -> float:
    return float(max(lo, min(hi, val)))


def lerp(a, b, t) -> float:
    t = max(0.0, min(1.0, t))
    return a + t * (b - a)


# ─────────────────────────────────────────────────────────────────────────────
# SEPSİS DURUM MAKİNESİ
# ─────────────────────────────────────────────────────────────────────────────

def build_sepsis_schedule(onset_sec, duration_sec, baseline, rng):
    prodrome_dur = min(21600, int((duration_sec - onset_sec) * 0.25))
    acute_dur    = min(86400, int((duration_sec - onset_sec) * 0.50))
    recovery_dur = (duration_sec - onset_sec) - prodrome_dur - acute_dur

    abd_prob_prodrome = 0.04 / 60
    abd_prob_acute    = 0.08 / 60
    abd_dur_range     = (120, 300)

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
            abd_elapsed  = 0

        is_abd = False
        if in_abd:
            is_abd = True; abd_elapsed += 1
            if abd_elapsed >= abd_duration:
                in_abd = False

        schedule[s] = {"phase": phase, "phase_t": phase_t, "is_abd": is_abd}

    return schedule


def sepsis_delta(schedule, sec, baseline, rng, ga_weeks, pna_days):
    info = schedule.get(sec)
    if info is None:
        return {"hr": 0, "rr": 0, "spo2": 0, "ecg": 0, "label": 0}

    if ga_weeks < 28:   ga_f = 1.6
    elif ga_weeks < 32: ga_f = 1.3
    elif ga_weeks < 36: ga_f = 1.1
    else:               ga_f = 1.0

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
    else:
        hr_d   = lerp(15 * ga_f, 0, t) + rng.normal(0, 2   * pna_noise)
        rr_d   = lerp(20 * ga_f, 0, t) + rng.normal(0, 1.5 * pna_noise)
        spo2_d = lerp(-10 * ga_f, 0, t) + rng.normal(0, 0.6 * pna_noise)
        ecg_d  = lerp(-0.15 * ga_f, 0, t)

    if is_abd:
        hr_d   -= rng.uniform(15 * ga_f, 35 * ga_f)
        spo2_d -= rng.uniform(5  * ga_f, 12 * ga_f)
        rr_d   -= rng.uniform(10 * ga_f, 25 * ga_f)

    return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 1}


# ─────────────────────────────────────────────────────────────────────────────
# APNEA DURUM MAKİNESİ
# ─────────────────────────────────────────────────────────────────────────────

def apnea_severity(ga_weeks, pna_days, pma_weeks):
    if pma_weeks >= 44: return 0.0
    pma_factor = 1.0 if pma_weeks < 36 else 1.0 - (pma_weeks - 36) / 8.0
    ga_factor  = 1.0 if ga_weeks < 28 else (0.75 if ga_weeks < 32 else 0.50)
    pna_factor = 1.0 if 14 <= pna_days <= 28 else (0.6 if pna_days < 7 else 0.8)
    return pma_factor * ga_factor * pna_factor


def build_apnea_schedule(ga_weeks, pna_days, pma_weeks, onset_sec, duration_sec, rng):
    severity = apnea_severity(ga_weeks, pna_days, pma_weeks)
    if severity == 0.0:
        return {}

    if ga_weeks < 28:
        apnea_prob = 0.40 * severity / 60
        dur_range    = (20, 60)
        recovery_sec = 300
        desat_target = rng.uniform(62, 72)
        brady_floor  = 0.60
        rr_min_apnea = 0.0
    elif ga_weeks < 32:
        apnea_prob = 0.30 * severity / 60
        dur_range    = (20, 45)
        recovery_sec = 240
        desat_target = rng.uniform(70, 78)
        brady_floor  = 0.65
        rr_min_apnea = 2.0
    else:
        apnea_prob = 0.20 * severity / 60
        dur_range    = (20, 35)
        recovery_sec = 180
        desat_target = rng.uniform(76, 83)
        brady_floor  = 0.70
        rr_min_apnea = 5.0

    SPO2_DELAY_SEC = 15

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

    schedule = {}
    for apnea_start, apnea_dur in events:
        pre_dur   = int(rng.integers(120, 300))
        pre_start = max(onset_sec, apnea_start - pre_dur)
        for s in range(pre_start, apnea_start):
            if s not in schedule:
                t = (s - pre_start) / max(pre_dur, 1)
                schedule[s] = {
                    "state": "PRE_APNEA", "phase_t": t,
                    "brady_floor": brady_floor, "rr_min": rr_min_apnea,
                }

        for elapsed in range(apnea_dur):
            s = apnea_start + elapsed
            if s >= duration_sec: break
            schedule[s] = {
                "state": "APNEA", "elapsed": elapsed,
                "duration": apnea_dur, "desat_target": desat_target,
                "brady_floor": brady_floor, "rr_min": rr_min_apnea,
                "recovery_sec": recovery_sec, "spo2_delay": SPO2_DELAY_SEC,
            }

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
        t = info["phase_t"]
        hr_d   = lerp(0, 6, t) + rng.normal(0, baseline["hr_std"]   * lerp(1.0, 2.5, t))
        rr_d   = rng.normal(0, baseline["rr_std"] * lerp(1.0, 3.0, t))
        spo2_d = rng.normal(0, baseline["spo2_std"] * lerp(1.0, 1.8, t))
        ecg_d  = rng.normal(0, 0.02)
        return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 0}

    if info["state"] == "APNEA":
        elapsed      = info["elapsed"]; duration = info["duration"]
        t            = elapsed / max(duration, 1)
        brady_floor  = hr_base * info["brady_floor"]
        desat_target = info["desat_target"]
        rr_min       = info["rr_min"]
        spo2_delay   = info["spo2_delay"]

        rr_d = (rr_base * (1 - t) + rr_min * t) - rr_base + rng.normal(0, 0.3)

        if elapsed < spo2_delay:
            spo2_d = rng.normal(0, 0.2)
        else:
            t2     = (elapsed - spo2_delay) / max(duration - spo2_delay, 1)
            spo2_d = (spo2_base * (1-t2) + desat_target * t2) - spo2_base + rng.normal(0, 0.5)

        current_spo2 = spo2_base + spo2_d
        if current_spo2 >= 80:
            hr_target = hr_base + 20 * min(t / 0.3, 1.0)
        else:
            brady_t   = clamp((80 - current_spo2) / 20, 0, 1)
            hr_target = brady_floor + (hr_base + 20 - brady_floor) * (1 - brady_t)
        hr_d  = hr_target - hr_base + rng.normal(0, 2)
        ecg_d = -0.15 * t + rng.normal(0, 0.02)
        return {"hr": hr_d, "rr": rr_d, "spo2": spo2_d, "ecg": ecg_d, "label": 1}

    else:  # RECOVERY
        step = info["recovery_step"]; dur = info["recovery_sec"]
        t    = (step + 1) / dur
        return {
            "hr":    (hr_base * info["brady_floor"] - hr_base) * (1 - clamp(t*0.8, 0, 1)) + rng.normal(0, 2),
            "rr":    (info["rr_min"] - rr_base) * (1 - t) + rng.normal(0, 0.8),
            "spo2":  (info["desat_target"] - spo2_base) * (1 - clamp(t*1.5, 0, 1)) + rng.normal(0, 0.5),
            "ecg":   -0.10 * (1 - t) + rng.normal(0, 0.01),
            "label": 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# KARDİYAK ANOMALİ DURUM MAKİNESİ
# ─────────────────────────────────────────────────────────────────────────────

def build_cardiac_schedule(onset_sec, duration_sec, cardiac_type, rng, ga_weeks):
    if ga_weeks < 28:
        svt_peak_range   = (90, 140); brady_peak_range = (50, 85); av_peak_range = (25, 45)
    elif ga_weeks < 32:
        svt_peak_range   = (80, 125); brady_peak_range = (43, 72); av_peak_range = (22, 38)
    elif ga_weeks < 36:
        svt_peak_range   = (72, 115); brady_peak_range = (38, 65); av_peak_range = (18, 32)
    else:
        svt_peak_range   = (65, 105); brady_peak_range = (32, 58); av_peak_range = (15, 28)

    if cardiac_type == "svt":
        interval_range = (60, 300);   dur_range = (60, 300)
    elif cardiac_type == "bradyarrhythmia":
        interval_range = (60, 300);   dur_range = (60, 300)
    elif cardiac_type == "av_block":
        interval_range = (120, 600);  dur_range = (120, 600)
    else:  # fluctuating
        interval_range = (60, 300);   dur_range = (60, 300)

    schedule = {}    
    s = onset_sec

    while s < duration_sec:
        wait = int(rng.integers(interval_range[0], interval_range[1]))
        s   += wait
        if s >= duration_sec: break

        ep_dur       = int(rng.integers(dur_range[0], dur_range[1]))
        onset_dur    = max(1, ep_dur // 5)
        peak_dur     = max(1, ep_dur // 2)
        recovery_dur = max(1, ep_dur - onset_dur - peak_dur)

        ep_subtype = str(rng.choice(["svt", "bradyarrhythmia"])) if cardiac_type == "fluctuating" else cardiac_type

        if ep_subtype == "svt":
            peak_hr   =  float(rng.uniform(*svt_peak_range))
            peak_spo2 = -float(rng.uniform(8, 15))
            peak_ecg  = -float(rng.uniform(0.30, 0.50))
            peak_rr   =  float(rng.uniform(5, 15))
        elif ep_subtype == "bradyarrhythmia":
            peak_hr   = -float(rng.uniform(*brady_peak_range))
            peak_spo2 = -float(rng.uniform(3, 12))
            peak_ecg  = -float(rng.uniform(0.20, 0.40))
            peak_rr   =  float(rng.uniform(-5, 5))
        else:
            peak_hr   = -float(rng.uniform(*av_peak_range))
            peak_spo2 = -float(rng.uniform(3, 8))
            peak_ecg  = -float(rng.uniform(0.15, 0.25))
            peak_rr   =  float(rng.uniform(-3, 3))

        pre_dur   = int(rng.integers(300, 900))
        pre_start = max(onset_sec, s - pre_dur)
        pre_hr    = lerp(0, peak_hr * 0.15, 1.0)
        for j in range(pre_start, s):
            if j not in schedule:
                t = (j - pre_start) / max(s - pre_start, 1)
                schedule[j] = {
                    "phase": "PRE_EPISODE", "phase_t": t, "subtype": ep_subtype,
                    "pre_hr": pre_hr,
                    "peak_hr": peak_hr, "peak_spo2": peak_spo2,
                    "peak_ecg": peak_ecg, "peak_rr": peak_rr,
                }

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

    phase    = info["phase"]; t = info["phase_t"]
    peak_hr  = info["peak_hr"]; peak_spo2 = info["peak_spo2"]
    peak_ecg = info["peak_ecg"]; peak_rr   = info["peak_rr"]

    if phase == "PRE_EPISODE":
        pre_hr = info["pre_hr"]
        hr_d   = lerp(0, pre_hr, t) + rng.normal(0, 3 * lerp(1.0, 2.0, t))
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
# ECG WAVEFORM — 25 Hz
# ─────────────────────────────────────────────────────────────────────────────

def build_ecg_waveform(duration_sec, baseline, cardiac_schedule, apnea_schedule,
                       sepsis_schedule, ga_weeks, seed):
    rng      = np.random.default_rng(seed + 777777)
    FS       = ECG_HZ
    n_samples = duration_sec * FS
    ecg      = np.zeros(n_samples)

    hr_base  = baseline["hr_mean"]
    amp_base = baseline["ecg_mean"]

    hr_per_sec = (
        np.full(duration_sec, hr_base)
        + rng.normal(0, baseline["hr_std"] * 0.3, duration_sec)
    )

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

    template_len  = int(FS * 0.5)
    t_arr         = np.linspace(0, 1, template_len)
    template_base = amp_base * (
        0.08 * np.exp(-((t_arr-0.15)**2)/(2*0.08**2)) +
        1.00 * np.exp(-((t_arr-0.35)**2)/(2*0.06**2)) +
        0.10 * np.exp(-((t_arr-0.65)**2)/(2*0.12**2))
    )

    beat_idx = 0
    while beat_idx < n_samples:
        sec = min(beat_idx // FS, duration_sec - 1)
        hr  = hr_per_sec[sec]
        rr  = max(2, int(60.0 / hr * FS))

        amp_factor = 1.0
        info_c = cardiac_schedule.get(sec)
        info_a = apnea_schedule.get(sec)
        if info_c:
            amp_factor += info_c["peak_ecg"] / amp_base * (
                info_c["phase_t"] if info_c["phase"] != "PEAK" else 1.0
            )
        if info_a and info_a["state"] == "APNEA":
            t = info_a["elapsed"] / max(info_a["duration"], 1)
            amp_factor -= 0.15 * t
        amp_factor = max(0.1, amp_factor)

        template = template_base * amp_factor
        jitter   = int(rng.normal(0, rr * 0.02))
        start    = beat_idx + jitter
        seg      = min(template_len, n_samples - start)
        if start >= 0 and seg > 0:
            ecg[start:start+seg] += template[:seg]
        beat_idx += rr

    t_full = np.arange(n_samples) / FS
    ecg   += 0.05 * amp_base * np.sin(2 * np.pi * 0.1 * t_full)
    ecg   += rng.normal(0, 0.015 * amp_base, n_samples)

    return np.round(ecg, 4)


# ─────────────────────────────────────────────────────────────────────────────
# LLD: Simulator sınıfı
# ─────────────────────────────────────────────────────────────────────────────

class Simulator:
    """
    LLD: Simulator
    Methods: generate() -> VitalMeasurement

    Her hasta için HR, SpO2, RR ve (isteğe bağlı) ECG üretir.
    """

    def __init__(self, config: ScenarioConfig):
        self.config   = config
        self.baseline = get_baseline(config.ga_weeks)
        self.pma      = compute_pma(config.ga_weeks, config.pna_days)
        self.rng      = np.random.default_rng(config.seed)

        # Schedule'ları önceden üret
        diseases     = config.diseases
        onset_map    = {d: int(v * 60) for d, v in diseases.items()}
        duration_sec = config.duration_seconds
        sched_rng    = np.random.default_rng(config.seed + 99999)

        self.sep_sched = (
            build_sepsis_schedule(onset_map.get("sepsis", 0), duration_sec,
                                  self.baseline, sched_rng)
            if "sepsis" in diseases else {}
        )
        self.apn_sched = (
            build_apnea_schedule(config.ga_weeks, config.pna_days, self.pma,
                                 onset_map.get("apnea", 0), duration_sec, sched_rng)
            if "apnea" in diseases else {}
        )
        self.card_sched = (
            build_cardiac_schedule(onset_map.get("cardiac", 0), duration_sec,
                                   config.cardiac_type or "svt", sched_rng,
                                   config.ga_weeks)
            if "cardiac" in diseases else {}
        )

    def generate(self, sec: int, start_time: datetime) -> list[dict]:
        """
        LLD: generate() -> VitalMeasurement
        Verilen saniye için tüm sinyal ölçümlerini üretir.
        """
        return _generate_second(
            sec         = sec,
            start_time  = start_time,
            config      = self.config,
            baseline    = self.baseline,
            pma_weeks   = self.pma,
            sep_sched   = self.sep_sched,
            apn_sched   = self.apn_sched,
            card_sched  = self.card_sched,
            rng         = np.random.default_rng(self.config.seed + sec * 7),
            is_healthy  = not bool(self.config.diseases),
        )


def _generate_second(sec, start_time, config, baseline, pma_weeks,
                     sep_sched, apn_sched, card_sched, rng, is_healthy):
    """Tek saniye için HR, SpO2 satırları üretir."""
    diseases = config.diseases
    ts       = (start_time + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_sec   = round(float(sec), 3)
    ga       = config.ga_weeks
    pna      = config.pna_days

    if pna <= 7:    bnf = 1.5
    elif pna <= 14: bnf = 1.2
    else:           bnf = 1.0

    hr   = baseline["hr_mean"]   + rng.normal(0, baseline["hr_std"]   * 0.4 * bnf)
    spo2 = baseline["spo2_mean"] + rng.normal(0, baseline["spo2_std"] * 0.4 * bnf)

    label_s = label_a = label_c = 0

    if "sepsis" in diseases:
        d = sepsis_delta(sep_sched, sec, baseline, rng, ga, pna)
        hr += d["hr"]; spo2 += d["spo2"]; label_s = d["label"]

    if "apnea" in diseases:
        d = apnea_delta(apn_sched, sec, baseline, rng)
        hr += d["hr"]; spo2 += d["spo2"]; label_a = d["label"]

    if "cardiac" in diseases:
        d = cardiac_delta(card_sched, sec, rng)
        hr += d["hr"]; spo2 += d["spo2"]; label_c = d["label"]

    # Concurrent etkileşimler
    if "sepsis" in diseases and "apnea" in diseases:
        sep_info = sep_sched.get(sec)
        apn_info = apn_sched.get(sec)
        if sep_info and apn_info:
            sep_active = sep_info.get("phase") in ("PRODROME", "ACUTE")
            apn_state  = apn_info.get("state", "")
            if apn_state == "APNEA" and sep_active:
                spo2 -= rng.uniform(2, 5)
                hr   += rng.uniform(5, 12)
            elif apn_state == "PRE_APNEA" and sep_active:
                hr -= rng.uniform(0, 4)

    # DÜZELTME: label_healthy hasta bazlı sabit — anlık sinyal durumuna göre değil
    # Hastalıklı hasta her zaman label_healthy=0, sağlıklı hasta her zaman 1
    label_h = 1 if is_healthy else 0

    hr   = round(clamp(hr,   50, 280), 1)
    spo2 = round(clamp(spo2, 65, 100), 1)
    is_valid_spo2 = spo2 >= baseline["spo2_min"] - 5

    common = {
        "measurementId":       str(uuid.uuid4()),
        "patientId":           config.patient_id,
        "timestamp":           ts,
        "gestationalAgeWeeks": ga,
        "postnatalAgeDays":    pna,
        "pma_weeks":           pma_weeks,
        "label_sepsis":        label_s,
        "label_apnea":         label_a,
        "label_cardiac":       label_c,
        "label_healthy":       label_h,
    }

    return [
        {**common, "timestamp_sec": ts_sec,
         "signalType": "HEART_RATE", "value": hr, "unit": "BPM", "isValid": True},
        {**common, "timestamp_sec": ts_sec,
         "signalType": "SPO2", "value": spo2, "unit": "%", "isValid": is_valid_spo2},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# HASTA ÜRETİCİ
# ─────────────────────────────────────────────────────────────────────────────

def generate_patient(config: ScenarioConfig, start_time: datetime,
                     output_dir: str, generate_ecg: bool = True):
 
    baseline     = get_baseline(config.ga_weeks)
    pma_weeks    = compute_pma(config.ga_weeks, config.pna_days)
    duration_sec = config.duration_seconds
    diseases     = config.diseases
    is_healthy   = not bool(diseases)

    sched_rng = np.random.default_rng(config.seed + 99999)
    onset_map = {d: int(v * 60) for d, v in diseases.items()}

    sep_sched = (
        build_sepsis_schedule(onset_map.get("sepsis", 0), duration_sec,
                              baseline, sched_rng)
        if "sepsis" in diseases else {}
    )
    apn_sched = (
        build_apnea_schedule(config.ga_weeks, config.pna_days, pma_weeks,
                             onset_map.get("apnea", 0), duration_sec, sched_rng)
        if "apnea" in diseases else {}
    )
    card_sched = (
        build_cardiac_schedule(onset_map.get("cardiac", 0), duration_sec,
                               config.cardiac_type or "svt", sched_rng,
                               config.ga_weeks)
        if "cardiac" in diseases else {}
    )

    if config.ga_weeks <= 7:    bnf = 1.5
    elif config.pna_days <= 14: bnf = 1.2
    else:                       bnf = 1.0

    hr_rows = []; spo2_rows = []; rr_rows = []

    # DÜZELTME: Tek rng nesnesi — her saniye default_rng() oluşturulmuyor
    main_rng = np.random.default_rng(config.seed)
    hr_noise   = main_rng.normal(0, baseline["hr_std"]   * 0.4 * bnf, duration_sec)
    spo2_noise = main_rng.normal(0, baseline["spo2_std"] * 0.4 * bnf, duration_sec)

    for s in range(duration_sec):
        rng_s = np.random.default_rng(config.seed + s * 7)
        ts    = (start_time + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_sec = round(float(s), 3)

        hr   = baseline["hr_mean"]   + hr_noise[s]
        spo2 = baseline["spo2_mean"] + spo2_noise[s]

        label_s = label_a = label_c = 0

        if "sepsis" in diseases:
            d = sepsis_delta(sep_sched, s, baseline, rng_s, config.ga_weeks, config.pna_days)
            hr += d["hr"]; spo2 += d["spo2"]; label_s = d["label"]

        if "apnea" in diseases:
            d = apnea_delta(apn_sched, s, baseline, rng_s)
            hr += d["hr"]; spo2 += d["spo2"]; label_a = d["label"]

        if "cardiac" in diseases:
            d = cardiac_delta(card_sched, s, rng_s)
            hr += d["hr"]; spo2 += d["spo2"]; label_c = d["label"]

        if "sepsis" in diseases and "apnea" in diseases:
            sep_info = sep_sched.get(s)
            apn_info = apn_sched.get(s)
            if sep_info and apn_info:
                sep_active = sep_info.get("phase") in ("PRODROME", "ACUTE")
                apn_state  = apn_info.get("state", "")
                if apn_state == "APNEA" and sep_active:
                    spo2 -= rng_s.uniform(2, 5)
                    hr   += rng_s.uniform(5, 12)
                elif apn_state == "PRE_APNEA" and sep_active:
                    hr -= rng_s.uniform(0, 4)

        # DÜZELTME: label_healthy hasta bazlı sabit
        label_h = 1 if is_healthy else 0

        hr   = round(clamp(hr,   50, 280), 1)
        spo2 = round(clamp(spo2, 65, 100), 1)
        is_valid_spo2 = spo2 >= baseline["spo2_min"] - 5

        common = {
            "measurementId":       str(uuid.uuid4()),
            "patientId":           config.patient_id,
            "timestamp":           ts,
            "gestationalAgeWeeks": config.ga_weeks,
            "postnatalAgeDays":    config.pna_days,
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

    # RR: 0.5 Hz
    rr_rng = np.random.default_rng(config.seed + 11111)
    for s in range(0, duration_sec, 2):
        rng_s  = np.random.default_rng(config.seed + s * 11)
        ts     = (start_time + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_sec = round(float(s), 3)

        rr     = baseline["rr_mean"] + rng_s.normal(0, baseline["rr_std"] * 0.4 * bnf)
        label_s = label_a = label_c = 0

        if "sepsis" in diseases:
            d = sepsis_delta(sep_sched, s, baseline, rng_s, config.ga_weeks, config.pna_days)
            rr += d["rr"]; label_s = d["label"]

        if "apnea" in diseases:
            d = apnea_delta(apn_sched, s, baseline, rng_s)
            rr += d["rr"]; label_a = d["label"]

        if "cardiac" in diseases:
            d = cardiac_delta(card_sched, s, rng_s)
            rr += d["rr"]; label_c = d["label"]

        if "sepsis" in diseases and "apnea" in diseases:
            sep_info = sep_sched.get(s)
            apn_info = apn_sched.get(s)
            if sep_info and apn_info:
                sep_active = sep_info.get("phase") in ("PRODROME", "ACUTE")
                apn_state  = apn_info.get("state", "")
                if apn_state == "PRE_APNEA" and sep_active:
                    # DÜZELTME: rr_boost dead code kaldırıldı — direkt RR güncelleniyor
                    rr += rng_s.choice([-5.0, 5.0]) * rng_s.random()

        label_h = 1 if is_healthy else 0
        rr      = round(clamp(rr, 0, 90), 1)

        common = {
            "measurementId":       str(uuid.uuid4()),
            "patientId":           config.patient_id,
            "timestamp":           ts,
            "gestationalAgeWeeks": config.ga_weeks,
            "postnatalAgeDays":    config.pna_days,
            "pma_weeks":           pma_weeks,
            "label_sepsis":        label_s,
            "label_apnea":         label_a,
            "label_cardiac":       label_c,
            "label_healthy":       label_h,
        }
        rr_rows.append({**common, "timestamp_sec": ts_sec,
                        "signalType": "RESP_RATE", "value": rr,
                        "unit": "breaths/min", "isValid": True})

    # DÜZELTME: ECG sadece generate_ecg=True ise üretiliyor (--no_ecg çalışıyor)
    if generate_ecg:
        ecg_signal = build_ecg_waveform(
            duration_sec, baseline, card_sched, apn_sched,
            sep_sched, config.ga_weeks, config.seed,
        )
        n_ecg    = len(ecg_signal)
        ts_secs  = np.round(np.arange(n_ecg) / ECG_HZ, 4)
        ecg_df   = pd.DataFrame({
            "timestamp_sec": ts_secs,
            "ecg_mv":        ecg_signal,
            "signal_type":   "ECG",
            "unit":          "mV",
            "patient_id":    config.patient_id,
        })
        ecg_path = os.path.join(output_dir, f"ecg_{config.patient_id[:8]}.csv")
        ecg_df.to_csv(ecg_path, index=False)

    return hr_rows, spo2_rows, rr_rows


# ─────────────────────────────────────────────────────────────────────────────
# HASTA TANIMLAMASI
# ─────────────────────────────────────────────────────────────────────────────

def assign_diseases(ga_weeks: int, is_healthy: bool,
                    duration_min: int, rng, forced_combo=None):
    if is_healthy:
        return {}, None

    if forced_combo is not None:
        selected = list(forced_combo)
    else:
        def apnea_weight(ga):
            if ga < 28:  return 0.85
            if ga < 32:  return 0.50
            if ga < 36:  return 0.25
            return 0.0   # DÜZELTME: DISEASE_GA_LIMITS kullanılıyor — 36+ apnea yok

        def sepsis_weight(ga): return 0.65 if ga < 32 else 0.55
        def cardiac_weight(ga): return 0.50

        weights  = {}
        # DÜZELTME: DISEASE_GA_LIMITS aktif — sınır dışındaki hastalıklar eklenmez
        for disease, (lo, hi) in DISEASE_GA_LIMITS.items():
            if lo <= ga_weeks < hi:
                if disease == "apnea":
                    w = apnea_weight(ga_weeks)
                elif disease == "sepsis":
                    w = sepsis_weight(ga_weeks)
                else:
                    w = cardiac_weight(ga_weeks)
                if w > 0:
                    weights[disease] = w

        selected = [d for d, w in weights.items() if rng.random() < w]

        if not selected and weights:
            all_d = list(weights.keys())
            all_w = np.array([weights[d] for d in all_d])
            all_w = all_w / all_w.sum()
            selected = [str(rng.choice(all_d, p=all_w))]
        elif not selected:
            selected = ["sepsis"]

    diseases     = {}
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
    parser.add_argument("--output_dir",     type=str,   default="data/all_data")
    parser.add_argument("--seed",           type=int,   default=42)
    # DÜZELTME: --no_ecg artık generate_patient'a bağlı ve çalışıyor
    parser.add_argument("--no_ecg",         action="store_true",
                        help="ECG waveform üretme (büyük dosya, test için)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    rng          = np.random.default_rng(args.seed)
    duration_min = int(args.duration_hours * 60)
    n_healthy    = int(args.n_patients * args.healthy_ratio)
    start_time   = datetime(2024, 1, 10, 8, 30, 0)
    generate_ecg = not args.no_ecg   # DÜZELTME: flag aktif

    print("=" * 60)
    print("Manifetch NICU — Unified Sentetik Veri Üretici v7")
    # DÜZELTME: ECG Hz tutarsızlığı giderildi — 25 Hz
    print(f"Örnekleme: HR/SpO2=1Hz, RR=0.5Hz, ECG={ECG_HZ}Hz"
          + (" [ECG KAPALI]" if not generate_ecg else ""))
    print("=" * 60)
    print(f"Hasta sayısı   : {args.n_patients}")
    print(f"Süre           : {args.duration_hours} saat")
    print(f"Sağlıklı oran  : {args.healthy_ratio:.0%}")
    print()

    n_sick = args.n_patients - n_healthy
    combos = [
        ["apnea"],
        ["apnea"],
        ["cardiac"],
        ["cardiac"],
        ["sepsis"],
        ["apnea", "cardiac"],
        ["apnea", "cardiac"],
        ["apnea", "sepsis"],
        ["cardiac", "sepsis"],
        ["cardiac", "sepsis"],
        ["apnea", "cardiac", "sepsis"],
        ["apnea", "cardiac", "sepsis"],
    ]
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
        diseases, cardiac_type = assign_diseases(
            ga_weeks, is_healthy, duration_min, rng, forced_combo=forced
        )

        key = (
            "healthy" if not diseases
            else (f"{list(diseases.keys())[0]}_only" if len(diseases) == 1 else "combined")
        )
        stats[key] = stats.get(key, 0) + 1

        patient_start = start_time + timedelta(seconds=i * 13)

        print(f"  [{i+1}/{args.n_patients}] GA={ga_weeks}w PNA={pna_days}d "
              f"diseases={list(diseases.keys())}...")

        config = ScenarioConfig(
            patient_id       = patient_id,
            duration_seconds = int(args.duration_hours * 3600),
            ga_weeks         = ga_weeks,
            pna_days         = pna_days,
            diseases         = diseases,
            cardiac_type     = cardiac_type,
            seed             = seed_p,
        )

        hr_rows, spo2_rows, rr_rows = generate_patient(
            config       = config,
            start_time   = patient_start,
            output_dir   = args.output_dir,
            generate_ecg = generate_ecg,   # DÜZELTME: flag bağlandı
        )

        all_hr.extend(hr_rows)
        all_spo2.extend(spo2_rows)
        all_rr.extend(rr_rows)

        metadata.append({
            "patientId":          patient_id,
            "gestationalAgeWeeks": ga_weeks,
            "postnatalAgeDays":   pna_days,
            "pma_weeks":          pma_weeks,
            "diseases":           list(diseases.keys()),
            "disease_onsets_min": diseases,
            "cardiac_type":       cardiac_type,
            "is_healthy":         is_healthy,
        })

    # all_vitals.csv
    print("\nall_vitals.csv oluşturuluyor...")
    all_rows = all_hr + all_spo2 + all_rr
    all_rows.sort(key=lambda r: (r["timestamp"], r["patientId"]))

    fieldnames = [
        "measurementId", "patientId", "timestamp", "timestamp_sec",
        "signalType", "value", "unit", "isValid",
        "gestationalAgeWeeks", "postnatalAgeDays", "pma_weeks",
        "label_sepsis", "label_apnea", "label_cardiac", "label_healthy",
    ]

    out_path = os.path.join(args.output_dir, "all_vitals.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # Metadata
    meta_path = os.path.join(args.output_dir, "patients_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at":    datetime.now().isoformat() + "Z",
            "version":         "v7",
            "sampling": {
                "HR_Hz":   HR_HZ,
                "SpO2_Hz": SPO2_HZ,
                "RR_Hz":   RR_HZ,
                "ECG_Hz":  ECG_HZ,   # DÜZELTME: 25 Hz (250 değil)
            },
            "n_patients":      args.n_patients,
            "duration_hours":  args.duration_hours,
            "healthy_ratio":   args.healthy_ratio,
            "ecg_generated":   generate_ecg,
            "patients":        metadata,
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
    # DÜZELTME: Doğru dosya adı ve Hz
    if generate_ecg:
        print(f"  ECG ({ECG_HZ} Hz): her hasta için ecg_<id[:8]>.csv")
    else:
        print("  ECG: [atlandı — --no_ecg aktif]")
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