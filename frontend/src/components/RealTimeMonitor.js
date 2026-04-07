import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';

export default function RealTimeMonitor({ patientId, alerts, setAlerts }) {
  const [vitals,  setVitals]  = useState({ HEART_RATE: null, SPO2: null, RESP_RATE: null });
  const [wsState, setWsState] = useState('connecting');
  const wsRef = useRef(null);
  const { user } = useAuth();
  const { t }    = useLang();
  const canAck   = ['DOCTOR', 'NURSE'].includes(user?.role);

  useEffect(() => {
    const ws = new WebSocket(`ws://127.0.0.1:8000/ws/vitals/${patientId}`);
    wsRef.current = ws;
    ws.onopen  = () => setWsState('connected');
    ws.onclose = () => setWsState('disconnected');
    ws.onerror = () => setWsState('error');
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'vital') {
        setVitals(prev => ({ ...prev, [msg.signal_type]: msg.value }));
      }
      if (msg.type === 'alert') {
        setAlerts(prev => {
          const exists = prev.find(a => a.alert_id === msg.data.alert_id);
          return exists ? prev : [msg.data, ...prev];
        });
      }
    };
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
    }, 25000);
    return () => { clearInterval(ping); ws.close(); };
  }, [patientId]);

  const handleAck = async (alertId) => {
    try {
      await api.acknowledgeAlert(alertId);
      setAlerts(prev => prev.map(a => a.alert_id === alertId ? { ...a, status: 'ACKNOWLEDGED' } : a));
    } catch (err) { console.error(err); }
  };

  const handleResolve = async (alertId) => {
    try {
      await api.resolveAlert(alertId);
      setAlerts(prev => prev.filter(a => a.alert_id !== alertId));
    } catch (err) { console.error(err); }
  };

  const VITALS_CONFIG = [
    { key: 'HEART_RATE', label: t.monitor.heartRate, unit: 'bpm',  min: 100, max: 180 },
    { key: 'SPO2',       label: t.monitor.spo2,       unit: '%',    min: 88,  max: 100 },
    { key: 'RESP_RATE',  label: t.monitor.respRate,   unit: '/min', min: 30,  max: 70  },
  ];

  const isAlert = (key, val) => {
    if (val === null) return false;
    const cfg = VITALS_CONFIG.find(v => v.key === key);
    return val < cfg.min || val > cfg.max;
  };

  const wsLabel = wsState === 'connected' ? t.monitor.wsConnected
    : wsState === 'connecting' ? t.monitor.wsConnecting
    : t.monitor.wsDisconnected;

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
        {VITALS_CONFIG.map(({ key, label, unit }) => {
          const val = vitals[key];
          const alerting = isAlert(key, val);
          return (
            <div key={key} className={`vital-card ${alerting ? 'alert' : 'normal'}`}>
              <div className="vital-label">{label}</div>
              <div className={`vital-value ${alerting ? 'alert' : 'normal'}`}>
                {val !== null ? val.toFixed(0) : '—'}
              </div>
              <div className="vital-unit">{unit}</div>
            </div>
          );
        })}
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <p style={{ fontWeight: 600, marginBottom: 12, color: 'var(--navy)' }}>{t.monitor.ecgWaveform}</p>
        <div style={{
          height: 120, background: 'var(--bg)', borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--text-muted)', fontSize: 13, fontStyle: 'italic',
        }}>
          {t.monitor.ecgPlaceholder}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
          background: wsState === 'connected' ? '#22c55e' : wsState === 'connecting' ? '#f59e0b' : '#e53935',
        }} />
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{wsLabel}</span>
      </div>

      {alerts.filter(a => a.status === 'ACTIVE').length > 0 && (
        <div className="card">
          <p style={{ fontWeight: 600, marginBottom: 12, color: 'var(--navy)' }}>
            {t.monitor.activeAlerts} ({alerts.filter(a => a.status === 'ACTIVE').length})
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {alerts.filter(a => a.status === 'ACTIVE').map(alert => (
              <div key={alert.alert_id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px', borderRadius: 8,
                background: alert.severity === 'HIGH' ? 'var(--danger-bg)' : 'var(--warning-bg)',
                borderLeft: `4px solid ${alert.severity === 'HIGH' ? 'var(--danger)' : 'var(--warning)'}`,
              }}>
                <div>
                  <span className={`badge badge-${alert.severity.toLowerCase()}`} style={{ marginRight: 10 }}>
                    {alert.severity}
                  </span>
                  <span style={{ fontSize: 13 }}>{new Date(alert.created_at).toLocaleTimeString()}</span>
                </div>
                {canAck && (
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-outline" style={{ padding: '4px 12px', fontSize: 12 }}
                      onClick={() => handleAck(alert.alert_id)}>{t.monitor.acknowledge}</button>
                    <button className="btn btn-danger" style={{ padding: '4px 12px', fontSize: 12 }}
                      onClick={() => handleResolve(alert.alert_id)}>{t.monitor.resolve}</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}