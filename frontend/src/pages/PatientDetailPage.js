import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Topbar from '../components/Topbar';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import RealTimeMonitor  from '../components/RealTimeMonitor';
import AIResultsTab     from '../components/AIResultsTab';
import TrendAnalysisTab from '../components/TrendAnalysisTab';
import ReportsTab       from '../components/ReportsTab';

function buildTabs(role, t) {
  const all = [
    { id: 'monitor', label: t.tabs.realTimeMonitor },
    { id: 'ai',      label: t.tabs.aiResults,      roles: ['DOCTOR'] },
    { id: 'trend',   label: t.tabs.trendAnalysis },
    { id: 'reports', label: t.tabs.reports,         roles: ['DOCTOR'] },
  ];
  return all.filter(tab => !tab.roles || tab.roles.includes(role));
}

function playAlertSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const playBeep = (startTime) => {
      const oscillator = ctx.createOscillator();
      const gainNode   = ctx.createGain();
      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(880, startTime);
      oscillator.frequency.setValueAtTime(660, startTime + 0.15);
      oscillator.frequency.setValueAtTime(880, startTime + 0.30);
      gainNode.gain.setValueAtTime(0.4, startTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + 0.5);
      oscillator.start(startTime);
      oscillator.stop(startTime + 0.5);
    };
    const now = ctx.currentTime;
    playBeep(now);
    playBeep(now + 0.7);
    playBeep(now + 1.4);
  } catch (e) {}
}

const SIGNAL_LABELS = {
  HEART_RATE: 'Kalp Atışı',
  SPO2:       'SpO₂',
  RESP_RATE:  'Solunum Hızı',
  ECG:        'ECG',
};

// ── Toast bileşeni ──────────────────────────────────────────────────────────

function AlertToast({ toasts, onAck, onDismiss }) {
  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 72,
      right: 24,
      zIndex: 1000,
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      maxWidth: 320,
    }}>
      {toasts.map(toast => {
        const isHigh  = toast.severity === 'HIGH';
        const bg      = isHigh ? '#c62828' : '#e65100';
        const signal  = toast.signal_type
          ? (SIGNAL_LABELS[toast.signal_type] || toast.signal_type)
          : 'AI Risk Alarmı';
        const timeStr = new Date(toast.created_at).toLocaleTimeString('tr-TR', {
          hour: '2-digit', minute: '2-digit', second: '2-digit'
        });

        return (
          <div key={toast.id} style={{
            background: bg,
            color: 'white',
            borderRadius: 10,
            padding: '14px 16px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
            animation: 'slideIn 0.25s ease',
            minWidth: 280,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>
                  {isHigh ? '⚠ KRİTİK ALERT' : '⚠ UYARI'}
                </p>
                <p style={{ fontSize: 15, fontWeight: 600, marginBottom: 2 }}>
                  {signal}
                </p>
                <p style={{ fontSize: 12, opacity: 0.85, marginBottom: 10 }}>
                  Önem: {toast.severity} &nbsp;·&nbsp; {timeStr}
                </p>
                <button
                  onClick={() => onAck(toast.alert_id, toast.id)}
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    border: '1.5px solid rgba(255,255,255,0.6)',
                    color: 'white',
                    borderRadius: 6,
                    padding: '5px 16px',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Onayla
                </button>
              </div>
              <button
                onClick={() => onDismiss(toast.id)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'rgba(255,255,255,0.75)',
                  fontSize: 18,
                  cursor: 'pointer',
                  lineHeight: 1,
                  padding: '0 0 0 12px',
                }}
              >
                ✕
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Ana sayfa ───────────────────────────────────────────────────────────────

export default function PatientDetailPage() {
  const { patientId } = useParams();
  const [patient,   setPatient]   = useState(null);
  const [activeTab, setActiveTab] = useState('monitor');
  const [loading,   setLoading]   = useState(true);
  const [toasts,    setToasts]    = useState([]);
  const { user }   = useAuth();
  const { t }      = useLang();
  const navigate   = useNavigate();

  const alertsRef       = useRef([]);
  const [alertsDisplay, setAlertsDisplay] = useState([]);
  const canAck = ['DOCTOR', 'NURSE'].includes(user?.role);

  const setAlerts = (updater) => {
    const next = typeof updater === 'function'
      ? updater(alertsRef.current)
      : updater;
    alertsRef.current = next;
    setAlertsDisplay(next);
  };

  const dismissToast = useCallback((toastId) => {
    setToasts(prev => prev.filter(t => t.id !== toastId));
  }, []);

  const ackFromToast = useCallback(async (alertId, toastId) => {
    try {
      await api.acknowledgeAlert(alertId);
      setAlerts(prev => prev.map(a =>
        a.alert_id === alertId ? { ...a, status: 'ACKNOWLEDGED' } : a
      ));
      dismissToast(toastId);
    } catch (err) { console.error(err); }
  }, [dismissToast]);

  useEffect(() => {
    if (user?.role === 'ADMINISTRATOR') {
      navigate('/admin', { replace: true });
    }
  }, [user, navigate]);

  const TABS = buildTabs(user?.role, t);

  useEffect(() => {
    const valid = TABS.find(tab => tab.id === activeTab);
    if (!valid && TABS.length > 0) {
      setActiveTab(TABS[0].id);
    }
  }, [user?.role]);

  useEffect(() => {
    api.getPatient(patientId)
      .then(r => setPatient(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => {
    const pollAlerts = () => {
      api.getAlerts(patientId)
        .then(r => {
          const incoming = r.data;
          const prev     = alertsRef.current;

          const prevIds   = new Set(prev.map(a => a.alert_id));
          const newAlerts = incoming.filter(a => !prevIds.has(a.alert_id));

          if (newAlerts.length > 0) {
            if (newAlerts.some(a => a.severity === 'HIGH')) {
              playAlertSound();
            }

            if (canAck) {
              const newToasts = newAlerts.map(a => ({
                id:          `${a.alert_id}_${Date.now()}`,
                alert_id:    a.alert_id,
                severity:    a.severity,
                signal_type: a.signal_type || null,
                created_at:  a.created_at,
              }));
              setToasts(prev => [...prev, ...newToasts]);

              // 15 saniye sonra otomatik kapat
              newToasts.forEach(toast => {
                setTimeout(() => dismissToast(toast.id), 15000);
              });
            }
          }

          const changed =
            incoming.length !== prev.length ||
            incoming.some((a, i) => a.alert_id !== prev[i]?.alert_id || a.status !== prev[i]?.status);

          if (changed) {
            alertsRef.current = incoming;
            setAlertsDisplay(incoming);
          }
        })
        .catch(() => {});
    };

    pollAlerts();
    const interval = setInterval(pollAlerts, 5000);
    return () => clearInterval(interval);
  }, [patientId, canAck]);

  const hasHighAlert = alertsDisplay.some(
    a => a.severity === 'HIGH' && a.status === 'ACTIVE'
  );
  const activeCount = alertsDisplay.filter(a => a.status === 'ACTIVE').length;

  if (loading) return (
    <div>
      <Topbar title={t.patientDetail.loading} />
      <div className="loading"><div className="spinner" />{t.patientDetail.loading}</div>
    </div>
  );

  return (
    <div>
      <Topbar title={patient ? `${t.patientDetail.patientInfo}: ${patient.full_name}` : t.patientDetail.loading} />

      <AlertToast
        toasts={toasts}
        onAck={ackFromToast}
        onDismiss={dismissToast}
      />

      <div className="page-content">
        <button
          className="btn btn-outline"
          onClick={() => navigate('/patients')}
          style={{ marginBottom: 16, display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          ← {t.patientDetail.backToList || 'Hasta Paneli'}
        </button>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div className="card" style={{ padding: '14px 18px' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 4 }}>{t.patientDetail.patientInfo}</p>
            <p style={{ fontWeight: 600 }}>{patient?.full_name}</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              {t.common.ga}: {patient?.gestational_age_weeks}{t.common.weeks}
              &nbsp;|&nbsp;
              {t.common.pna}: {patient?.postnatal_age_days}{t.common.days}
            </p>
          </div>

          <div className="card" style={{ padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 10, height: 10, background: '#22c55e', borderRadius: '50%', display: 'inline-block' }} />
            <div>
              <p style={{ fontWeight: 600, color: 'var(--teal)' }}>{t.patientDetail.deviceConnected}</p>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.patientDetail.monitoringActive}</p>
            </div>
          </div>

          <div className="card" style={{
            padding: '14px 18px',
            background: hasHighAlert ? 'var(--danger)' : 'var(--success-bg)',
            border: hasHighAlert ? 'none' : '1.5px solid var(--success)',
          }}>
            {hasHighAlert ? (
              <>
                <p style={{ color: 'white', fontWeight: 700, fontSize: 14 }}>{t.patientDetail.criticalAlert}</p>
                <p style={{ color: 'rgba(255,255,255,0.9)', fontSize: 12 }}>
                  HIGH — {activeCount} {t.patientDetail.activeAlerts}
                </p>
              </>
            ) : (
              <>
                <p style={{ color: 'var(--teal)', fontWeight: 700, fontSize: 14 }}>{t.patientDetail.noCriticalAlerts}</p>
                <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>{activeCount} {t.patientDetail.activeAlerts}</p>
              </>
            )}
          </div>
        </div>

        <div className="tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'monitor'  && (
          <RealTimeMonitor
            patientId={patientId}
            patient={patient}
            alerts={alertsDisplay}
            setAlerts={setAlerts}
          />
        )}
        {activeTab === 'ai'      && <AIResultsTab     patientId={patientId} />}
        {activeTab === 'trend'   && <TrendAnalysisTab patientId={patientId} patient={patient} />}
        {activeTab === 'reports' && <ReportsTab       patientId={patientId} patient={patient} />}
      </div>

      <style>{`
        @keyframes slideIn {
          from { transform: translateX(120%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </div>
  );
}