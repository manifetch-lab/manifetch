import { useState } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function ReportsTab({ patientId, patient }) {
  const [days,    setDays]    = useState(7);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const { user } = useAuth();
  const canReport = user?.role === 'DOCTOR';

  const handleGenerate = async () => {
    setError('');
    setLoading(true);
    try {
      const res = await api.getReport(patientId, days);
      const url  = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href  = url;
      link.download = `report_${patientId.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError('Report generation failed.');
    } finally {
      setLoading(false);
    }
  };

  if (!canReport) return (
    <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>
      Report generation requires Doctor role.
    </div>
  );

  const fromDate = new Date(Date.now() - days * 24 * 3600 * 1000);
  const toDate   = new Date();

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {/* Config */}
      <div className="card">
        <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>Report Configuration</h3>

        <div className="form-group">
          <label className="form-label">Date Range</label>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>From:</span>
              <input className="form-input" type="text" readOnly
                value={fromDate.toISOString().slice(0, 10)} style={{ width: 140 }} />
            </div>
            <div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>To:</span>
              <input className="form-input" type="text" readOnly
                value={toDate.toISOString().slice(0, 10)} style={{ width: 140 }} />
            </div>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Period</label>
          <select className="form-input" value={days} onChange={e => setDays(Number(e.target.value))} style={{ width: '100%' }}>
            <option value={1}>Last 1 day</option>
            <option value={3}>Last 3 days</option>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, fontWeight: 500, marginBottom: 10, color: 'var(--navy)' }}>Include in Report</p>
          {[
            'Patient demographic information',
            'Vital signs summary and trends',
            'Critical alerts and events log',
            'AI assessment results',
          ].map(item => (
            <p key={item} style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>
              ✓ {item}
            </p>
          ))}
        </div>

        {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

        <button
          className="btn btn-primary"
          onClick={handleGenerate}
          disabled={loading}
          style={{ width: '100%', justifyContent: 'center', padding: 12 }}
        >
          {loading ? 'Generating...' : 'Generate PDF Report'}
        </button>
      </div>

      {/* Preview */}
      <div className="card" style={{ background: 'var(--bg)' }}>
        <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>Report Preview</h3>
        <div style={{
          background: 'white', borderRadius: 8, padding: 24,
          boxShadow: 'var(--shadow)', minHeight: 300,
          fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.8,
        }}>
          <p style={{ fontWeight: 700, color: 'var(--navy)', marginBottom: 8 }}>NICU Clinical Report</p>
          <p>Patient: {patient?.full_name}</p>
          <p>GA: {patient?.gestational_age_weeks}w &nbsp;|&nbsp; PNA: {patient?.postnatal_age_days}d</p>
          <p>Date Range: {fromDate.toLocaleDateString()} – {toDate.toLocaleDateString()}</p>
          <hr style={{ margin: '12px 0', border: 'none', borderTop: '1px solid var(--border)' }} />
          <p>[Report content preview]</p>
          <br />
          <p>Vital Signs Summary</p>
          <p>AI Assessment Results</p>
          <p>Alert History</p>
          <p>...</p>
        </div>
      </div>
    </div>
  );
}