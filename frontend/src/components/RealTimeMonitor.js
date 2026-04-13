import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { api } from '../api/client';
import ECGCanvas from './ECGCanvas';

const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://127.0.0.1:8000';

const GA_THRESHOLDS = {
  '24-29': { HEART_RATE: { min: 120, max: 177 }, SPO2: { min: 88, max: 98 }, RESP_RATE: { min: 30, max: 75 } },
  '29-33': { HEART_RATE: { min: 122, max: 175 }, SPO2: { min: 89, max: 98 }, RESP_RATE: { min: 30, max: 70 } },
  '33-37': { HEART_RATE: { min: 115, max: 172 }, SPO2: { min: 90, max: 99 }, RESP_RATE: { min: 30, max: 68 } },
  '37-43': { HEART_RATE: { min: 100, max: 160 }, SPO2: { min: 92, max: 100 }, RESP_RATE: { min: 30, max: 65 } },
};

function getGaThreshold(ga, signalType) {
  if (!ga) return null;
  const key = ga < 29 ? '24-29' : ga < 33 ? '29-33' : ga < 37 ? '33-37' : '37-43';
  return GA_THRESHOLDS[key]?.[signalType] || null;
}

export default function RealTimeMonitor({ patientId, patient, alerts, setAlerts }) {
  const [vitals,     setVitals]     = useState({ HEART_RATE: null, SPO2: null, RESP_RATE: null });
  const [wsState,    setWsState]    = useState('connecting');
  const [thresholds, setThresholds] = useState({});
  const wsRef = useRef(null);
  const { user } = useAuth();
  const { t }    = useLang();
  const canAck   = ['DOCTOR', 'NURSE'].includes(user?.role);

  useEffect(() => {
    if (!patient?.gestational_age_weeks) return;
    const ga = patient.gestational_age_weeks;
    const fallback = {
      HEART_RATE: getGaThreshold(ga, 'HEART_RATE') || { min: 100, max: 180 },
      SPO2:       getGaThreshold(ga, 'SPO2')       || { min: 88,  max: 100 },
      RESP_RATE:  getGaThreshold(ga, 'RESP_RATE')  || { min: 30,  max: 70  },
    };
    setThresholds(fallback);
  }, [patient]);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      const token = sessionStorage.getItem('token');
      if (!token || cancelled) return;

      const ws = new WebSocket(`${WS_BASE}/ws/vitals/${patientId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ token }));
        setWsState('connected');
      };

      ws.onclose = () => {
        setWsState('disconnected');
        if (!cancelled) setTimeout(connect, 3000);
      };

      ws.onerror = () => setWsState('error');

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'vital') {
          setVitals(prev => ({ ...prev, [msg.signal_type]: msg.value }));
        }
      };
    };

    setWsState('connecting');
    connect();

    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 25000);

    return () => {
      cancelled = true;
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [patientId]);

  const handleAck = async (alertId) => {
    try {
      await api.acknowledgeAlert(alertId);
      setAlerts(prev => prev.map(a =>
        a.alert_id === alertId ? { ...a, status: 'ACKNOWLEDGED' } : a
      ));
    } catch (err) { console.error(err); }
  };

  const handleResolve = async (alertId) => {
    try {
      await api.resolveAlert(alertId);
      setAlerts(prev => prev.filter(a => a.alert_id !== alertId));
    } catch (err) { console.error(err); }
  };

  const VITALS_CONFIG = [
    { key: 'HEART_RATE', label: t.monitor.heartRate, unit: 'bpm'  },
    { key: 'SPO2',       label: t.monitor.spo2,       unit: '%'    },
    { key: 'RESP_RATE',  label: t.monitor.respRate,   unit: '/min' },
  ];

  const isAlert = (key, val) => {
    if (val === null) return false;
    const thr = thresholds[key];
    if (!thr) return false;
    return val < thr.min || val > thr.max;
  };

  const wsLabel = wsState === 'connected'   ? t.monitor.wsConnected
    : wsState === 'connecting' ? t.monitor.wsConnecting
    : t.monitor.wsDisconnected;

  const visibleAlerts = alerts.filter(a => a.status === 'ACTIVE' || a.status === 'ACKNOWLEDGED');

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
        {VITALS_CONFIG.map(({ key, label, unit }) => {
          const val      = vitals[key];
          const alerting = isAlert(key, val);
          const thr      = thresholds[key];
          return (
            <div key={key} className={`vital-card ${alerting ? 'alert' : 'normal'}`}>
              <div className="vital-label">{label}</div>
              <div className={`vital-value ${alerting ? 'alert' : 'normal'}`}>
                {val !== null ? val.toFixed(0) : '—'}
              </div>
              <div className="vital-unit">{unit}</div>
              {thr && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                  {thr.min} – {thr.max} {unit}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <ECGCanvas patientId={patientId} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
          background: wsState === 'connected' ? '#22c55e' : wsState === 'connecting' ? '#f59e0b' : '#e53935',
        }} />
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{wsLabel}</span>
      </div>

      {visibleAlerts.length > 0 && (
        <div className="card">
          <p style={{ fontWeight: 600, marginBottom: 12, color: 'var(--navy)' }}>
            {t.monitor.activeAlerts} ({visibleAlerts.length})
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {visibleAlerts.map(alert => (
              <div key={alert.alert_id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px', borderRadius: 8,
                background: alert.status === 'ACKNOWLEDGED' ? 'var(--bg)' : alert.severity === 'HIGH' ? 'var(--danger-bg)' : 'var(--warning-bg)',
                borderLeft: `4px solid ${alert.status === 'ACKNOWLEDGED' ? 'var(--border)' : alert.severity === 'HIGH' ? 'var(--danger)' : 'var(--warning)'}`,
              }}>
                <div>
                  <span className={`badge badge-${alert.severity.toLowerCase()}`} style={{ marginRight: 10 }}>
                    {alert.severity}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 8 }}>
                    {alert.status}
                  </span>
                  <span style={{ fontSize: 13 }}>{new Date(alert.created_at).toLocaleTimeString()}</span>
                </div>
                {canAck && (
                  <div style={{ display: 'flex', gap: 8 }}>
                    {alert.status === 'ACTIVE' && (
                      <button className="btn btn-outline" style={{ padding: '4px 12px', fontSize: 12 }}
                        onClick={() => handleAck(alert.alert_id)}>
                        {t.monitor.acknowledge}
                      </button>
                    )}
                    {alert.status === 'ACKNOWLEDGED' && (
                      <button className="btn btn-danger" style={{ padding: '4px 12px', fontSize: 12 }}
                        onClick={() => handleResolve(alert.alert_id)}>
                        {t.monitor.resolve}
                      </button>
                    )}
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