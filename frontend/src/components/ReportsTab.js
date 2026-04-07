import { useState } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';

export default function ReportsTab({ patientId, patient }) {
  const [days,    setDays]    = useState(7);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const [confirm, setConfirm] = useState(false);
  const { user } = useAuth();
  const { t }    = useLang();
  const canReport = user?.role === 'DOCTOR';

  const handleGenerate = async () => {
    setConfirm(false);
    setError('');
    setLoading(true);
    try {
      const res = await api.getReport(patientId, days);
      const patientName = patient?.full_name?.replace(/\s+/g, '_') || patientId.slice(0, 8);
      const date = new Date().toISOString().slice(0, 10);
      const url  = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href  = url;
      link.download = `NICU_Report_${patientName}_${date}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t.reports.error);
    } finally {
      setLoading(false);
    }
  };

  if (!canReport) return (
    <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>
      {t.reports.noPermission}
    </div>
  );

  const fromDate = new Date(Date.now() - days * 24 * 3600 * 1000);
  const toDate   = new Date();

  return (
    <div>
      {/* Onay modalı */}
      {confirm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999,
        }}>
          <div className="card" style={{ width: 400, textAlign: 'center' }}>
            <h3 style={{ marginBottom: 12, color: 'var(--navy)' }}>{t.reports.confirmTitle}</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: 20, fontSize: 14 }}>
              {days} {t.reports.last7d.split(' ')[1]} {t.reports.confirmMsg}
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button className="btn btn-primary" onClick={handleGenerate}>{t.reports.confirmYes}</button>
              <button className="btn btn-outline" onClick={() => setConfirm(false)}>{t.reports.confirmNo}</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="card">
          <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>{t.reports.config}</h3>
          <div className="form-group">
            <label className="form-label">{t.reports.dateRange}</label>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>{t.reports.from}</span>
                <input className="form-input" type="text" readOnly value={fromDate.toISOString().slice(0, 10)} style={{ width: 140 }} />
              </div>
              <div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>{t.reports.to}</span>
                <input className="form-input" type="text" readOnly value={toDate.toISOString().slice(0, 10)} style={{ width: 140 }} />
              </div>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">{t.reports.period}</label>
            <select className="form-input" value={days} onChange={e => setDays(Number(e.target.value))} style={{ width: '100%' }}>
              <option value={1}>{t.reports.last1d}</option>
              <option value={3}>{t.reports.last3d}</option>
              <option value={7}>{t.reports.last7d}</option>
              <option value={14}>{t.reports.last14d}</option>
              <option value={30}>{t.reports.last30d}</option>
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <p style={{ fontSize: 13, fontWeight: 500, marginBottom: 10, color: 'var(--navy)' }}>{t.reports.include}</p>
            {t.reports.items.map(item => (
              <p key={item} style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>✓ {item}</p>
            ))}
          </div>
          {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}
          <button
            className="btn btn-primary"
            onClick={() => setConfirm(true)}
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: 12 }}
          >
            {loading ? t.reports.generating : t.reports.generate}
          </button>
        </div>

        <div className="card" style={{ background: 'var(--bg)' }}>
          <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>{t.reports.preview}</h3>
          <div style={{ background: 'white', borderRadius: 8, padding: 24, boxShadow: 'var(--shadow)', minHeight: 300, fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.8 }}>
            <p style={{ fontWeight: 700, color: 'var(--navy)', marginBottom: 8 }}>{t.reports.previewTitle}</p>
            <p>{t.patientList.name}: {patient?.full_name}</p>
            <p>{t.common.ga}: {patient?.gestational_age_weeks}{t.common.weeks} | {t.common.pna}: {patient?.postnatal_age_days}{t.common.days}</p>
            <p>{t.reports.dateRange}: {fromDate.toLocaleDateString()} – {toDate.toLocaleDateString()}</p>
            <hr style={{ margin: '12px 0', border: 'none', borderTop: '1px solid var(--border)' }} />
            <p>{t.reports.previewContent}</p>
            <br />
            <p>{t.reports.vitalSummary}</p>
            <p>{t.reports.aiResults}</p>
            <p>{t.reports.alertHistory}</p>
            <p>...</p>
          </div>
        </div>
      </div>
    </div>
  );
}