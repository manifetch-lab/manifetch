import json
import asyncio
from typing import Dict, Set
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.websockets import WebSocketState
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.db.models import VitalMeasurement, Alert
from backend.db.enums import AlertStatus

router = APIRouter(tags=["websocket"])


# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    """WebSocket bağlantı yöneticisi."""

    def __init__(self):
        # patient_id → set of WebSocket
        self.vital_connections:  Dict[str, Set[WebSocket]] = {}
        self.alert_connections:  Dict[str, Set[WebSocket]] = {}
        self.global_connections: Set[WebSocket] = set()

    # ── Vital connections ─────────────────────────────────────────────────────

    async def connect_vitals(self, websocket: WebSocket, patient_id: str):
        await websocket.accept()
        if patient_id not in self.vital_connections:
            self.vital_connections[patient_id] = set()
        self.vital_connections[patient_id].add(websocket)
        print(f"[WS] Vitals bağlandı: {patient_id[:8]} "
              f"(toplam: {len(self.vital_connections[patient_id])})")

    def disconnect_vitals(self, websocket: WebSocket, patient_id: str):
        if patient_id in self.vital_connections:
            self.vital_connections[patient_id].discard(websocket)
            if not self.vital_connections[patient_id]:
                del self.vital_connections[patient_id]

    async def broadcast_vital(self, patient_id: str, data: dict):
        """Belirtilen hastanın tüm vital bağlantılarına yayın yap."""
        if patient_id not in self.vital_connections:
            return
        message  = json.dumps(data, default=str)
        dead     = set()
        for ws in self.vital_connections[patient_id].copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.vital_connections[patient_id].discard(ws)

    # ── Alert connections ─────────────────────────────────────────────────────

    async def connect_alerts(self, websocket: WebSocket, patient_id: str):
        await websocket.accept()
        if patient_id not in self.alert_connections:
            self.alert_connections[patient_id] = set()
        self.alert_connections[patient_id].add(websocket)
        print(f"[WS] Alerts bağlandı: {patient_id[:8]}")

    def disconnect_alerts(self, websocket: WebSocket, patient_id: str):
        if patient_id in self.alert_connections:
            self.alert_connections[patient_id].discard(websocket)
            if not self.alert_connections[patient_id]:
                del self.alert_connections[patient_id]

    async def broadcast_alert(self, patient_id: str, alert_data: dict):
        """Alert bildirimini ilgili hasta kanalına yayınla."""
        if patient_id not in self.alert_connections:
            return
        message = json.dumps({"type": "alert", "data": alert_data}, default=str)
        dead    = set()
        for ws in self.alert_connections[patient_id].copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.alert_connections[patient_id].discard(ws)

    # ── Global connections ────────────────────────────────────────────────────

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.global_connections.add(websocket)
        print(f"[WS] Global bağlandı (toplam: {len(self.global_connections)})")

    def disconnect_global(self, websocket: WebSocket):
        self.global_connections.discard(websocket)

    async def broadcast_global(self, data: dict):
        """Tüm global bağlantılara yayın yap."""
        if not self.global_connections:
            return
        message = json.dumps(data, default=str)
        dead    = set()
        for ws in self.global_connections.copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.global_connections.discard(ws)

    def get_stats(self) -> dict:
        return {
            "vital_channels":    len(self.vital_connections),
            "alert_channels":    len(self.alert_connections),
            "global_clients":    len(self.global_connections),
            "total_vital_conns": sum(len(v) for v in self.vital_connections.values()),
        }


# Singleton manager
manager = ConnectionManager()


# ── WebSocket Endpoint'leri ───────────────────────────────────────────────────

@router.websocket("/ws/vitals/{patient_id}")
async def websocket_vitals(
    websocket:  WebSocket,
    patient_id: str,
):
    """
    Canlı vital sinyal akışı.
    Frontend buraya bağlanarak gerçek zamanlı HR, SpO2, RR verisi alır.

    Mesaj formatı:
    {
        "type": "vital",
        "patient_id": "...",
        "signal_type": "HEART_RATE",
        "value": 145.0,
        "unit": "BPM",
        "timestamp": "2024-01-10T...",
        "timestamp_sec": 3600.0,
        "is_valid": true
    }
    """
    await manager.connect_vitals(websocket, patient_id)
    try:
        # Bağlantı onay mesajı
        await websocket.send_text(json.dumps({
            "type":       "connected",
            "patient_id": patient_id,
            "message":    "Vital stream bağlantısı kuruldu.",
            "timestamp":  datetime.utcnow().isoformat(),
        }))

        # Bağlantıyı açık tut
        while True:
            try:
                # Frontend'den ping bekle veya disconnect
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type":      "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    }))
            except asyncio.TimeoutError:
                # 30 sn'de bir keepalive
                await websocket.send_text(json.dumps({
                    "type":      "keepalive",
                    "timestamp": datetime.utcnow().isoformat(),
                }))
    except WebSocketDisconnect:
        manager.disconnect_vitals(websocket, patient_id)
        print(f"[WS] Vitals bağlantısı kesildi: {patient_id[:8]}")
    except Exception as e:
        manager.disconnect_vitals(websocket, patient_id)
        print(f"[WS] Vitals hata: {e}")


@router.websocket("/ws/alerts/{patient_id}")
async def websocket_alerts(
    websocket:  WebSocket,
    patient_id: str,
):
    """
    Anlık alert bildirimleri.

    Mesaj formatı:
    {
        "type": "alert",
        "data": {
            "alert_id": "...",
            "severity": "HIGH",
            "status": "ACTIVE",
            "created_at": "...",
            "signal_type": "HEART_RATE"
        }
    }
    """
    await manager.connect_alerts(websocket, patient_id)
    try:
        await websocket.send_text(json.dumps({
            "type":       "connected",
            "patient_id": patient_id,
            "message":    "Alert stream bağlantısı kuruldu.",
            "timestamp":  datetime.utcnow().isoformat(),
        }))

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type":      "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    }))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type":      "keepalive",
                    "timestamp": datetime.utcnow().isoformat(),
                }))
    except WebSocketDisconnect:
        manager.disconnect_alerts(websocket, patient_id)
        print(f"[WS] Alerts bağlantısı kesildi: {patient_id[:8]}")
    except Exception as e:
        manager.disconnect_alerts(websocket, patient_id)


@router.websocket("/ws/stream")
async def websocket_global(websocket: WebSocket):
    """
    Tüm hastaların global akışı.
    Dashboard overview için — tüm vital ve alertler buradan akar.
    """
    await manager.connect_global(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type":    "connected",
            "message": "Global stream bağlantısı kuruldu.",
            "stats":   manager.get_stats(),
        }))

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type":      "pong",
                        "stats":     manager.get_stats(),
                        "timestamp": datetime.utcnow().isoformat(),
                    }))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type":      "keepalive",
                    "stats":     manager.get_stats(),
                    "timestamp": datetime.utcnow().isoformat(),
                }))
    except WebSocketDisconnect:
        manager.disconnect_global(websocket)
    except Exception as e:
        manager.disconnect_global(websocket)


# ── Yardımcı Fonksiyonlar (ingestion.py tarafından çağrılır) ──────────────────

async def notify_vital(measurement) -> None:
    """Yeni vital ölçümü tüm ilgili bağlantılara yayınla."""
    data = {
        "type":           "vital",
        "patient_id":     measurement.patient_id,
        "signal_type":    measurement.signal_type,
        "value":          measurement.value,
        "unit":           measurement.unit,
        "timestamp":      measurement.timestamp.isoformat() if measurement.timestamp else None,
        "timestamp_sec":  measurement.timestamp_sec,
        "is_valid":       measurement.is_valid,
    }
    await manager.broadcast_vital(measurement.patient_id, data)
    await manager.broadcast_global({**data, "source": "vital"})


async def notify_alert(alert) -> None:
    """Yeni alert'i ilgili bağlantılara yayınla."""
    data = {
        "alert_id":   alert.alert_id,
        "patient_id": alert.patient_id,
        "severity":   alert.severity,
        "status":     alert.status,
        "rule_id":    alert.rule_id,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }
    await manager.broadcast_alert(alert.patient_id, data)
    await manager.broadcast_global({"type": "alert", "data": data, "source": "alert"})