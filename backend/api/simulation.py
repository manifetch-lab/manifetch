import subprocess
import sys
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.api.auth import require_any_role
from backend.db.models import User

router = APIRouter(prefix="/simulation", tags=["simulation"])

# Aktif simülasyon process'leri — patient_id → subprocess
_processes: dict[str, subprocess.Popen] = {}


class SimulationStartDTO(BaseModel):
    patient_id: str
    scenario:   str = "normal"
    duration:   int = 60
    speed:      float = 1.0
    seed:       int = 42


@router.post("/start")
def start_simulation(
    payload:      SimulationStartDTO,
    current_user: User = Depends(require_any_role),
):
    if payload.scenario not in ["normal", "sepsis", "apnea", "cardiac", "mixed"]:
        raise HTTPException(status_code=400, detail="Geçersiz senaryo.")

    if payload.patient_id in _processes:
        proc = _processes[payload.patient_id]
        if proc.poll() is None:
            raise HTTPException(status_code=409, detail="Bu hasta için simülasyon zaten çalışıyor.")

    # DÜZELTME: Hardcoded fallback kaldırıldı — env'de yoksa hata fırlat
    username = os.getenv("STREAM_USERNAME")
    password = os.getenv("STREAM_PASSWORD")

    if not username or not password:
        raise HTTPException(
            status_code=500,
            detail="STREAM_USERNAME ve STREAM_PASSWORD environment variable'ları ayarlanmamış."
        )

    cmd = [
        sys.executable, "-m", "data_simulation.stream_publisher",
        "--patient_id", payload.patient_id,
        "--scenario",   payload.scenario,
        "--duration",   str(payload.duration // 60),
        "--speed",      str(payload.speed),
        "--seed",       str(payload.seed),
        "--username",   username,
        "--password",   password,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    _processes[payload.patient_id] = proc

    return {
        "status":     "started",
        "patient_id": payload.patient_id,
        "scenario":   payload.scenario,
        "duration":   payload.duration,
        "pid":        proc.pid,
    }


@router.post("/stop")
def stop_simulation(
    patient_id:   str,
    current_user: User = Depends(require_any_role),
):
    proc = _processes.get(patient_id)
    if not proc or proc.poll() is not None:
        raise HTTPException(status_code=404, detail="Bu hasta için aktif simülasyon yok.")

    proc.terminate()
    _processes.pop(patient_id, None)
    return {"status": "stopped", "patient_id": patient_id}


@router.get("/status")
def simulation_status(
    current_user: User = Depends(require_any_role),
):
    result = {}
    for pid, proc in list(_processes.items()):
        if proc.poll() is None:
            result[pid] = {"status": "running", "pid": proc.pid}
        else:
            result[pid] = {"status": "finished"}
    return result