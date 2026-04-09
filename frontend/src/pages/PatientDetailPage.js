import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import Topbar from '../components/Topbar';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import RealTimeMonitor from '../components/RealTimeMonitor';
import AIResultsTab from '../components/AIResultsTab';
import TrendAnalysisTab from '../components/TrendAnalysisTab';
import ReportsTab from '../components/ReportsTab';

export default function PatientDetailPage() {
  const { patientId } = useParams();
  const [patient,  setPatient]  = useState(null);
  const [alerts,   setAlerts]   = useState([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab,      setTab]      = useState(() => parseInt(searchParams.get('tab') || '0', 10));
  const [loading,  setLoading]  = useState(true);
  const { user }   = useAuth();
  const { t }      = useLang();
  const navigate   = useNavigate();

  useEffect(() => {
    if (user?.role === 'ADMINISTRATOR') {
      navigate('/admin', { replace: true });
    }
  }, [user, navigate]);

  const TABS = user?.role === 'NURSE'
    ? [t.tabs.realTimeMonitor, t.tabs.trendAnalysis, t.tabs.reports]
    : [t.tabs.realTimeMonitor, t.tabs.aiResults, t.tabs.trendAnalysis, t.tabs.reports];

  const getTabContent = (tabIdx) => {
    if (user?.role === 'NURSE') {
      return ['monitor', 'trend', 'reports'][tabIdx];
    }
    return ['monitor', 'ai', 'trend', 'reports'][tabIdx];
  };

  useEffect(() => {
    Promise.all([
      api.getPatient(patientId),
      api.getAlerts(patientId, 'ACTIVE'),
    ]).then(([pRes, aRes]) => {
      setPatient(pRes.data);
      setAlerts(aRes.data);
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, [patientId]);

  const hasHighAlert = alerts.some(a => a.severity === 'HIGH');

  if (loading) return (
    <div>
      <Topbar title={t.patientDetail.loading} />
      <div className="loading"><div className="spinner" />{t.patientDetail.loading}</div>
    </div>
  );

  const activeTab = getTabContent(tab);

  return (
    <div>
      <Topbar title={patient ? `${t.patientDetail.patientInfo}: ${patient.full_name}` : t.patientDetail.loading} />
      <div className="page-content">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div className="card" style={{ padding: '14px 18px' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 4 }}>{t.patientDetail.patientInfo}</p>
            <p style={{ fontWeight: 600 }}>{patient?.full_name}</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              {t.common.ga}: {patient?.gestational_age_weeks}{t.common.weeks} &nbsp;|&nbsp; {t.common.pna}: {patient?.postnatal_age_days}{t.common.days}
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
          {TABS.map((tabName, i) => (
            <button key={tabName} className={`tab ${tab === i ? 'active' : ''}`} onClick={() => { setTab(i); setSearchParams({ tab: i }); }}>
              {tabName}
            </button>
          ))}
        </div>

        {activeTab === 'monitor' && <RealTimeMonitor patientId={patientId} alerts={alerts} setAlerts={setAlerts} />}
        {activeTab === 'ai'      && <AIResultsTab    patientId={patientId} />}
        {activeTab === 'trend'   && <TrendAnalysisTab patientId={patientId} />}
        {activeTab === 'reports' && <ReportsTab       patientId={patientId} patient={patient} />}
      </div>
    </div>
  );
}