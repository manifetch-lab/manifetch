import json
import asyncio
from typing import Dict, Set
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from sqlalchemy.orm import Session

from backend.db.base import SessionLocal

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        self.vital_connections:  Dict[str, Set[WebSocket]] = {}
        self.alert_connections:  Dict[str, Set[WebSocket]] = {}
        self.ecg_connections:    Dict[str, Set[WebSocket]] = {}
        self.global_connections: Set[WebSocket] = set()

    async def connect_vitals(self, websocket, patient_id):
        self.vital_connections.setdefault(patient_id, set()).add(websocket)

    def disconnect_vitals(self, websocket, patient_id):
        self.vital_connections.get(patient_id, set()).discard(websocket)

    async def broadcast_vital(self, patient_id, data):
        message = json.dumps(data, default=str)
        dead = set()
        for ws in self.vital_connections.get(patient_id, set()).copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.vital_connections.get(patient_id, set()).discard(ws)

    async def connect_alerts(self, websocket, patient_id):
        self.alert_connections.setdefault(patient_id, set()).add(websocket)

    def disconnect_alerts(self, websocket, patient_id):
        self.alert_connections.get(patient_id, set()).discard(websocket)

    async def broadcast_alert(self, patient_id, alert_data):
        message = json.dumps({"type": "alert", "data": alert_data}, default=str)
        dead = set()
        for ws in self.alert_connections.get(patient_id, set()).copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.alert_connections.get(patient_id, set()).discard(ws)

    async def connect_ecg(self, websocket, patient_id):
        self.ecg_connections.setdefault(patient_id, set()).add(websocket)

    def disconnect_ecg(self, websocket, patient_id):
        self.ecg_connections.get(patient_id, set()).discard(websocket)

    async def broadcast_ecg(self, patient_id, samples):
        message = json.dumps({"type": "ecg", "patient_id": patient_id, "samples": samples})
        dead = set()
        for ws in self.ecg_connections.get(patient_id, set()).copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.ecg_connections.get(patient_id, set()).discard(ws)

    async def connect_global(self, websocket):
        self.global_connections.add(websocket)

    def disconnect_global(self, websocket):
        self.global_connections.discard(websocket)

    async def broadcast_global(self, data):
        if not self.global_connections:
            return
        message = json.dumps(data, default=str)
        dead = set()
        for ws in self.global_connections.copy():
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.global_connections.discard(ws)

    def get_stats(self):
        return {
            "vital_channels":    len(self.vital_connections),
            "alert_channels":    len(self.alert_connections),
            "ecg_channels":      len(self.ecg_connections),
            "global_clients":    len(self.global_connections),
            "total_vital_conns": sum(len(v) for v in self.vital_connections.values()),
        }


manager = ConnectionManager()


async def _authenticate_ws_first_message(websocket: WebSocket, timeout: float = 5.0):
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        data = json.loads(raw)
        token = data.get("token", "")
    except asyncio.TimeoutError:
        try:
            await websocket.close(code=1008, reason="Auth timeout.")
        except Exception:
            pass
        return None
    except Exception:
        return None

    db = SessionLocal()
    try:
        from backend.api.auth import verify_ws_token
        user = verify_ws_token(token, db)
        if user is None:
            try:
                await websocket.close(code=1008, reason="Geçersiz token.")
            except Exception:
                pass
            return None
        return user
    finally:
        db.close()


@router.websocket("/ws/vitals/{patient_id}")
async def websocket_vitals(
    websocket:  WebSocket,
    patient_id: str,
):
    await websocket.accept()
    user = await _authenticate_ws_first_message(websocket)
    if not user:
        return

    await manager.connect_vitals(websocket, patient_id)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected", "patient_id": patient_id,
            "message": "Vital stream bağlantısı kuruldu.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "keepalive",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        manager.disconnect_vitals(websocket, patient_id)
    except Exception:
        manager.disconnect_vitals(websocket, patient_id)


@router.websocket("/ws/alerts/{patient_id}")
async def websocket_alerts(
    websocket:  WebSocket,
    patient_id: str,
):
    await websocket.accept()
    user = await _authenticate_ws_first_message(websocket)
    if not user:
        return

    await manager.connect_alerts(websocket, patient_id)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected", "patient_id": patient_id,
            "message": "Alert stream bağlantısı kuruldu.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "keepalive",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        manager.disconnect_alerts(websocket, patient_id)
    except Exception:
        manager.disconnect_alerts(websocket, patient_id)


@router.websocket("/ws/ecg/{patient_id}")
async def websocket_ecg(
    websocket:  WebSocket,
    patient_id: str,
):
    await websocket.accept()
    user = await _authenticate_ws_first_message(websocket)
    if not user:
        return

    await manager.connect_ecg(websocket, patient_id)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected", "patient_id": patient_id, "fs": 25,
        }))
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "keepalive"}))
    except WebSocketDisconnect:
        manager.disconnect_ecg(websocket, patient_id)
    except Exception:
        manager.disconnect_ecg(websocket, patient_id)


@router.websocket("/ws/stream")
async def websocket_global(
    websocket: WebSocket,
):
    await websocket.accept()
    user = await _authenticate_ws_first_message(websocket)
    if not user:
        return

    await manager.connect_global(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Global stream bağlantısı kuruldu.",
            "stats": manager.get_stats(),
        }))
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg  = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "stats": manager.get_stats(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "keepalive",
                    "stats": manager.get_stats(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        manager.disconnect_global(websocket)
    except Exception:
        manager.disconnect_global(websocket)


async def notify_vital(measurement) -> None:
    data = {
        "type": "vital", "patient_id": measurement.patient_id,
        "signal_type": measurement.signal_type, "value": measurement.value,
        "unit": measurement.unit,
        "timestamp": measurement.timestamp.isoformat() if measurement.timestamp else None,
        "timestamp_sec": measurement.timestamp_sec, "is_valid": measurement.is_valid,
    }
    await manager.broadcast_vital(measurement.patient_id, data)
    await manager.broadcast_global({**data, "source": "vital"})


async def notify_alert(alert) -> None:
    data = {
        "alert_id": alert.alert_id, "patient_id": alert.patient_id,
        "severity": alert.severity, "status": alert.status,
        "rule_id": alert.rule_id,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }
    await manager.broadcast_alert(alert.patient_id, data)
    await manager.broadcast_global({"type": "alert", "data": data, "source": "alert"})


async def notify_ecg(patient_id: str, samples: list) -> None:
    await manager.broadcast_ecg(patient_id, samples)