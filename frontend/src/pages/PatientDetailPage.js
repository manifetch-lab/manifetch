import { useState, useEffect } from 'react';
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
      const gainNode = ctx.createGain();
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

export default function PatientDetailPage() {
  const { patientId } = useParams();
  const [patient,   setPatient]   = useState(null);
  const [alerts,    setAlerts]    = useState([]);
  const [activeTab, setActiveTab] = useState('monitor');
  const [loading,   setLoading]   = useState(true);
  const { user }   = useAuth();
  const { t }      = useLang();
  const navigate   = useNavigate();

  useEffect(() => {
    if (user?.role === 'ADMINISTRATOR') {
      navigate('/admin', { replace: true });
    }
  }, [user, navigate]);

  const TABS = buildTabs(user?.role, t);

  useEffect(() => {
    const valid = TABS.find(t => t.id === activeTab);
    if (!valid && TABS.length > 0) {
      setActiveTab(TABS[0].id);
    }
  }, [user?.role]);

  // Hasta bilgisini çek
  useEffect(() => {
    api.getPatient(patientId)
      .then(r => setPatient(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [patientId]);

  // Alert polling — sayfa düzeyinde, her 5 saniyede bir
  useEffect(() => {
    const pollAlerts = () => {
      api.getAlerts(patientId, 'ACTIVE')
        .then(r => {
          setAlerts(prev => {
            const prevIds = new Set(prev.map(a => a.alert_id));
            const incoming = r.data.filter(a => !prevIds.has(a.alert_id));
            if (incoming.some(a => a.severity === 'HIGH')) {
              playAlertSound();
            }
            return r.data;
          });
        })
        .catch(() => {});
    };

    pollAlerts();
    const interval = setInterval(pollAlerts, 5000);
    return () => clearInterval(interval);
  }, [patientId]);

  const hasHighAlert = alerts.some(a => a.severity === 'HIGH');

  if (loading) return (
    <div>
      <Topbar title={t.patientDetail.loading} />
      <div className="loading"><div className="spinner" />{t.patientDetail.loading}</div>
    </div>
  );

  return (
    <div>
      <Topbar title={patient ? `${t.patientDetail.patientInfo}: ${patient.full_name}` : t.patientDetail.loading} />
      <div className="page-content">

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
                  {alerts[0]?.severity} — {alerts.length} {t.patientDetail.activeAlerts}
                </p>
              </>
            ) : (
              <>
                <p style={{ color: 'var(--teal)', fontWeight: 700, fontSize: 14 }}>{t.patientDetail.noCriticalAlerts}</p>
                <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>{alerts.length} {t.patientDetail.activeAlerts}</p>
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
            alerts={alerts}
            setAlerts={setAlerts}
          />
        )}
        {activeTab === 'ai'      && <AIResultsTab     patientId={patientId} />}
        {activeTab === 'trend'   && <TrendAnalysisTab patientId={patientId} patient={patient} />}
        {activeTab === 'reports' && <ReportsTab       patientId={patientId} patient={patient} />}
      </div>
    </div>
  );
}