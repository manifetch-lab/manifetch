import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { useLang } from '../context/LanguageContext';

export default function AIResultsTab({ patientId }) {
  const [results,  setResults]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const { t } = useLang();

  const load = () => {
    setLoading(true);
    api.getAIResults(patientId)
      .then(r => setResults(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
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

  if (loading) return <div className="loading"><div className="spinner" />{t.ai.loading}</div>;

  if (!latest) return (
    <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>
      {t.ai.noResults}
    </div>
  );

  const colors = riskColor(latest.risk_level);
  let shap = null;
  try {
    shap = latest.shap_values_json ? JSON.parse(latest.shap_values_json) : null;
  } catch {}

  const diseaseScores = [
    { key: 'sepsis',  label: 'Sepsis',  score: latest.sepsis_score  ?? 0, label_val: latest.sepsis_label  ?? 0, color: '#e53935' },
    { key: 'apnea',   label: 'Apnea',   score: latest.apnea_score   ?? 0, label_val: latest.apnea_label   ?? 0, color: '#f59e0b' },
    { key: 'cardiac', label: 'Cardiac', score: latest.cardiac_score ?? 0, label_val: latest.cardiac_label ?? 0, color: '#1e6eb5' },
  ];

  return (
    <div>
      {/* Genel risk kartı */}
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
          <div style={{
            background: colors.bg, color: colors.text,
            padding: '12px 24px', borderRadius: 8, fontWeight: 700, fontSize: 16,
          }}>
            {riskLabel(latest.risk_level)}
          </div>
          <div>
            <p style={{ fontWeight: 500 }}>
              {t.ai.riskScore}: {latest.risk_score.toFixed(2)} {t.ai.scale}
            </p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              {t.ai.model}: {latest.model_used}
            </p>
          </div>
        </div>
      </div>

      {/* Multi-label hastalık skorları */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>{t.ai.diseaseScores}</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {diseaseScores.map(({ key, label, score, label_val, color }) => (
            <div key={key} style={{
              padding: '14px 16px', borderRadius: 8,
              background: label_val ? `${color}18` : 'var(--bg)',
              border: `1.5px solid ${label_val ? color : 'var(--border)'}`,
            }}>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</p>
              <p style={{
                fontSize: 26, fontWeight: 700,
                fontFamily: 'DM Mono, monospace',
                color: label_val ? color : 'var(--text)',
              }}>
                {(score * 100).toFixed(1)}%
              </p>
              {label_val === 1 && (
                <span style={{
                  fontSize: 11, fontWeight: 600,
                  color, background: `${color}22`,
                  padding: '2px 8px', borderRadius: 12,
                  display: 'inline-block', marginTop: 4,
                }}>
                  ⚠ Pozitif
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* SHAP açıklama kartı */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ color: 'var(--navy)', marginBottom: 12 }}>{t.ai.clinical}</h3>
        {shap ? (
          <div>
            <p style={{ fontWeight: 500, marginBottom: 8 }}>{t.ai.topFeatures}:</p>
            {Object.entries(shap).map(([disease, features]) => (
              <div key={disease} style={{ marginBottom: 12 }}>
                <p style={{
                  fontSize: 13, fontWeight: 600, color: 'var(--teal)',
                  marginBottom: 6, textTransform: 'capitalize',
                }}>
                  {disease}
                </p>
                {Array.isArray(features) && features.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: 13, width: 200, color: 'var(--text-muted)' }}>{f.feature}</span>
                    <div style={{ flex: 1, height: 6, background: 'var(--bg)', borderRadius: 3 }}>
                      <div style={{
                        height: '100%', borderRadius: 3, background: 'var(--teal)',
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
          <p style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>
            {t.ai.disclaimer}
          </p>
        )}
      </div>

      {/* Geçmiş sonuçlar tablosu */}
      {results.length > 1 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t.ai.timestamp}</th>
                <th>{t.ai.riskScore}</th>
                <th>Sepsis</th>
                <th>Apnea</th>
                <th>Cardiac</th>
                <th>{t.ai.title}</th>
              </tr>
            </thead>
            <tbody>
              {results.slice(1).map(r => (
                <tr key={r.result_id}>
                  <td>{new Date(r.timestamp).toLocaleString()}</td>
                  <td style={{ fontFamily: 'DM Mono, monospace' }}>{r.risk_score.toFixed(3)}</td>
                  <td style={{ fontFamily: 'DM Mono, monospace', color: r.sepsis_label  ? 'var(--danger)'  : 'inherit' }}>
                    {((r.sepsis_score  ?? 0) * 100).toFixed(1)}%
                  </td>
                  <td style={{ fontFamily: 'DM Mono, monospace', color: r.apnea_label   ? 'var(--warning)' : 'inherit' }}>
                    {((r.apnea_score   ?? 0) * 100).toFixed(1)}%
                  </td>
                  <td style={{ fontFamily: 'DM Mono, monospace', color: r.cardiac_label ? '#1e6eb5'        : 'inherit' }}>
                    {((r.cardiac_score ?? 0) * 100).toFixed(1)}%
                  </td>
                  <td>
                    <span className={`badge badge-${r.risk_level.toLowerCase()}`}>
                      {riskLabel(r.risk_level)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}