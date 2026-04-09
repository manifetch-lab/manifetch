import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { useLang } from '../context/LanguageContext';

export default function AIResultsTab({ patientId }) {
  const [results,  setResults]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const wsRef = useRef(null);
  const { t } = useLang();

  const load = () => {
    setLoading(true);
    api.getAIResults(patientId)
      .then(r => setResults(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, [patientId]);

  // WebSocket: AI sonucu gelince otomatik guncelle
  useEffect(() => {
    const ws = new WebSocket(`ws://127.0.0.1:8000/ws/vitals/${patientId}`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'ai_result' && msg.patient_id === patientId) {
        load();
      }
    };
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
    }, 25000);
    return () => { clearInterval(ping); ws.close(); };
  }, [patientId]);

  const latest = results[0];
  const riskColor = (level) => {
    if (level === 'HIGH')   return { bg: 'var(--danger)',  text: 'white' };
    if (level === 'MEDIUM') return { bg: 'var(--warning)', text: 'white' };
    return                         { bg: 'var(--teal)',    text: 'white' };
  };

  const riskLabel = (level) => {
    if (level === 'HIGH')   return t.ai.highRisk;
    if (level === 'MEDIUM') return t.ai.mediumRisk;
    return t.ai.lowRisk;
  };

  const riskDesc = (level) => {
    if (level === 'HIGH')   return t.ai.highDesc;
    if (level === 'MEDIUM') return t.ai.mediumDesc;
    return t.ai.lowDesc;
  };

  if (loading) return <div className="loading"><div className="spinner" />{t.ai.loading}</div>;

  if (!latest) return (
    <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>
      {t.ai.noResults}
    </div>
  );

  const colors = riskColor(latest.risk_level);
  let shap = null;
  try { shap = latest.shap_values_json ? JSON.parse(latest.shap_values_json) : null; } catch {}

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h3 style={{ color: 'var(--navy)', marginBottom: 4 }}>{t.ai.title}</h3>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {t.ai.timestamp}: {new Date(latest.timestamp).toLocaleString()}
            </p>
          </div>
          <button className="btn btn-outline" onClick={load}>{t.ai.refresh}</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: 16 }}>
          <div style={{ background: colors.bg, color: colors.text, padding: '12px 24px', borderRadius: 8, fontWeight: 700, fontSize: 16 }}>
            {riskLabel(latest.risk_level)}
          </div>
          <div>
            <p style={{ fontWeight: 500 }}>{t.ai.riskScore}: {latest.risk_score.toFixed(2)} {t.ai.scale}</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{t.ai.model}: {latest.model_used}</p>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ color: 'var(--navy)', marginBottom: 12 }}>{t.ai.clinical}</h3>
        {shap ? (
          <div>
            <p style={{ fontWeight: 500, marginBottom: 8 }}>{t.ai.topFeatures}:</p>
            {Object.entries(shap).map(([disease, features]) => (
              <div key={disease} style={{ marginBottom: 12 }}>
                <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--teal)', marginBottom: 6, textTransform: 'capitalize' }}>
                  {disease}
                </p>
                {Array.isArray(features) && features.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: 13, width: 200, color: 'var(--text-muted)' }}>{f.feature}</span>
                    <div style={{ flex: 1, height: 6, background: 'var(--bg)', borderRadius: 3 }}>
                      <div style={{ height: '100%', borderRadius: 3, background: 'var(--teal)', width: `${Math.min(f.importance * 100, 100)}%` }} />
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 50 }}>{f.importance.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div>
            <p style={{ marginBottom: 8 }}>{riskDesc(latest.risk_level)}</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>{t.ai.disclaimer}</p>
          </div>
        )}
      </div>

      {results.length > 1 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.ai.timestamp}</th>
                <th>{t.ai.riskScore}</th>
                <th>{t.ai.title}</th>
                <th>{t.ai.model}</th>
              </tr>
            </thead>
            <tbody>
              {results.slice(1).map(r => (
                <tr key={r.result_id}>
                  <td>{new Date(r.timestamp).toLocaleString()}</td>
                  <td style={{ fontFamily: 'DM Mono, monospace' }}>{r.risk_score.toFixed(3)}</td>
                  <td><span className={`badge badge-${r.risk_level.toLowerCase()}`}>{riskLabel(r.risk_level)}</span></td>
                  <td style={{ color: 'var(--text-muted)' }}>{r.model_used}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}