import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Topbar from '../components/Topbar';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import RealTimeMonitor from '../components/RealTimeMonitor';
import AIResultsTab from '../components/AIResultsTab';
import TrendAnalysisTab from '../components/TrendAnalysisTab';
import ReportsTab from '../components/ReportsTab';

export default function PatientDetailPage() {
  const { patientId } = useParams();
  const [patient,  setPatient]  = useState(null);
  const [alerts,   setAlerts]   = useState([]);
  const [tab,      setTab]      = useState(0);
  const [loading,  setLoading]  = useState(true);
  const { user }   = useAuth();
  const navigate   = useNavigate();

  // Admin hasta sayfasına giremez
  useEffect(() => {
    if (user?.role === 'ADMINISTRATOR') {
      navigate('/admin', { replace: true });
    }
  }, [user, navigate]);

  // Nurse için tab listesi — AI Results yok
  const TABS = user?.role === 'NURSE'
    ? ['Real-Time Monitor', 'Trend Analysis', 'Reports']
    : ['Real-Time Monitor', 'AI Results', 'Trend Analysis', 'Reports'];

  // Tab index mapping — Nurse'te AI Results yok, index kayması var
  const getTabContent = (tabIdx) => {
    if (user?.role === 'NURSE') {
      const nurseMap = ['monitor', 'trend', 'reports'];
      return nurseMap[tabIdx];
    }
    const doctorMap = ['monitor', 'ai', 'trend', 'reports'];
    return doctorMap[tabIdx];
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
      <Topbar title="Patient Detail" />
      <div className="loading"><div className="spinner" />Loading...</div>
    </div>
  );

  const activeTab = getTabContent(tab);

  return (
    <div>
      <Topbar title={patient ? `Patient: ${patient.full_name}` : 'Patient Detail'} />
      <div className="page-content">

        {/* Info + Alert row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div className="card" style={{ padding: '14px 18px' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 4 }}>Patient Info</p>
            <p style={{ fontWeight: 600 }}>{patient?.full_name}</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              GA: {patient?.gestational_age_weeks}w &nbsp;|&nbsp; PNA: {patient?.postnatal_age_days}d
            </p>
          </div>
          <div className="card" style={{ padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 10, height: 10, background: '#22c55e', borderRadius: '50%', display: 'inline-block' }} />
            <div>
              <p style={{ fontWeight: 600, color: 'var(--teal)' }}>Device Connected</p>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Real-time monitoring active</p>
            </div>
          </div>
          <div className="card" style={{
            padding: '14px 18px',
            background: hasHighAlert ? 'var(--danger)' : 'var(--success-bg)',
            border: hasHighAlert ? 'none' : '1.5px solid var(--success)',
          }}>
            {hasHighAlert ? (
              <>
                <p style={{ color: 'white', fontWeight: 700, fontSize: 14 }}>⚠ CRITICAL ALERT</p>
                <p style={{ color: 'rgba(255,255,255,0.9)', fontSize: 12 }}>
                  {alerts[0]?.severity} severity — {alerts.length} active alert(s)
                </p>
              </>
            ) : (
              <>
                <p style={{ color: 'var(--teal)', fontWeight: 700, fontSize: 14 }}>✓ No Critical Alerts</p>
                <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>{alerts.length} active alert(s)</p>
              </>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {TABS.map((t, i) => (
            <button key={t} className={`tab ${tab === i ? 'active' : ''}`} onClick={() => setTab(i)}>
              {t}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'monitor' && <RealTimeMonitor patientId={patientId} alerts={alerts} setAlerts={setAlerts} />}
        {activeTab === 'ai'      && <AIResultsTab    patientId={patientId} />}
        {activeTab === 'trend'   && <TrendAnalysisTab patientId={patientId} />}
        {activeTab === 'reports' && <ReportsTab       patientId={patientId} patient={patient} />}
      </div>
    </div>
  );
}