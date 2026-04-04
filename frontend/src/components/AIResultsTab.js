import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function AIResultsTab({ patientId }) {
  const [results,  setResults]  = useState([]);
  const [loading,  setLoading]  = useState(true);

  const load = () => {
    setLoading(true);
    api.getAIResults(patientId)
      .then(r => setResults(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, [patientId]);

  const latest = results[0];

  const riskColor = (level) => {
    if (level === 'HIGH')   return { bg: 'var(--danger)',  text: 'white' };
    if (level === 'MEDIUM') return { bg: 'var(--warning)', text: 'white' };
    return                         { bg: 'var(--teal)',    text: 'white' };
  };

  if (loading) return <div className="loading"><div className="spinner" />Loading AI results...</div>;

  if (!latest) return (
    <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>
      No AI results yet.
    </div>
  );

  const colors = riskColor(latest.risk_level);
  let shap = null;
  try { shap = latest.shap_values_json ? JSON.parse(latest.shap_values_json) : null; } catch {}

  return (
    <div>
      {/* Latest result */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h3 style={{ color: 'var(--navy)', marginBottom: 4 }}>AI Risk Assessment</h3>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Analysis Timestamp: {new Date(latest.timestamp).toLocaleString()}
            </p>
          </div>
          <button className="btn btn-outline" onClick={load}>↻ Refresh</button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: 16 }}>
          <div style={{
            background: colors.bg, color: colors.text,
            padding: '12px 24px', borderRadius: 8, fontWeight: 700, fontSize: 16,
          }}>
            {latest.risk_level} RISK
          </div>
          <div>
            <p style={{ fontWeight: 500 }}>Risk Score: {latest.risk_score.toFixed(2)} (Scale: 0-1)</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Model: {latest.model_used}</p>
          </div>
        </div>
      </div>

      {/* SHAP / Clinical interpretation */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ color: 'var(--navy)', marginBottom: 12 }}>Clinical Interpretation</h3>
        {shap ? (
          <div>
            <p style={{ fontWeight: 500, marginBottom: 8 }}>Top Contributing Features:</p>
            {Object.entries(shap).map(([disease, features]) => (
              <div key={disease} style={{ marginBottom: 12 }}>
                <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--teal)', marginBottom: 6, textTransform: 'capitalize' }}>
                  {disease}
                </p>
                {Array.isArray(features) && features.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: 13, width: 200, color: 'var(--text-muted)' }}>{f.feature}</span>
                    <div style={{ flex: 1, height: 6, background: 'var(--bg)', borderRadius: 3 }}>
                      <div style={{
                        height: '100%', borderRadius: 3,
                        background: 'var(--teal)',
                        width: `${Math.min(f.importance * 100, 100)}%`,
                      }} />
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 50 }}>
                      {f.importance.toFixed(3)}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div>
            <p style={{ marginBottom: 8 }}>
              {latest.risk_level === 'HIGH'
                ? 'The AI model has identified a concerning pattern in the patient\'s vital signs. Immediate clinical assessment is recommended.'
                : latest.risk_level === 'MEDIUM'
                ? 'The AI model has detected some abnormal patterns. Close monitoring is advised.'
                : 'Vital signs are within acceptable ranges. Continue routine monitoring.'}
            </p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>
              Note: This AI-generated assessment is intended to support, not replace, clinical judgment.
            </p>
          </div>
        )}
      </div>

      {/* History */}
      {results.length > 1 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Risk Score</th>
                <th>Risk Level</th>
                <th>Model</th>
              </tr>
            </thead>
            <tbody>
              {results.slice(1).map(r => (
                <tr key={r.result_id}>
                  <td>{new Date(r.timestamp).toLocaleString()}</td>
                  <td style={{ fontFamily: 'DM Mono, monospace' }}>{r.risk_score.toFixed(3)}</td>
                  <td><span className={`badge badge-${r.risk_level.toLowerCase()}`}>{r.risk_level}</span></td>
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