import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { api } from '../api/client';
import { useLang } from '../context/LanguageContext';

export default function TrendAnalysisTab({ patientId }) {
  const [rangeIdx, setRangeIdx] = useState(1);
  const [data,     setData]     = useState({});
  const [stats,    setStats]    = useState({});
  const [loading,  setLoading]  = useState(true);
  const { t } = useLang();

  const TIME_RANGES = [
    { label: t.trend.last6h,  hours: 6   },
    { label: t.trend.last24h, hours: 24  },
    { label: t.trend.last7d,  hours: 168 },
  ];

  const SIGNALS = [
    { key: 'HEART_RATE', label: t.trend.heartRateTrend, unit: 'bpm', color: '#1a9b8c', refMin: 100, refMax: 180 },
    { key: 'SPO2',       label: t.trend.spo2Trend,      unit: '%',   color: '#1e6eb5', refMin: 88,  refMax: 100 },
  ];

  useEffect(() => {
    setLoading(true);
    const hours = TIME_RANGES[rangeIdx].hours;
    Promise.all(
      SIGNALS.map(s => api.getTrends(patientId, s.key, hours))
    ).then(results => {
      const newData = {}; const newStats = {};
      SIGNALS.forEach((s, i) => {
        const rows = results[i].data;
        const step = Math.max(1, Math.floor(rows.length / 200));
        newData[s.key] = rows.filter((_, idx) => idx % step === 0).map(r => ({ t: r.timestamp_sec, val: r.value }));
        if (rows.length > 0) {
          const vals = rows.map(r => r.value);
          newStats[s.key] = {
            avg: (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1),
            min: Math.min(...vals).toFixed(1),
            max: Math.max(...vals).toFixed(1),
          };
        }
      });
      setData(newData); setStats(newStats);
    }).catch(console.error).finally(() => setLoading(false));
  }, [patientId, rangeIdx]);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-muted)' }}>{t.trend.timeRange}</span>
        {TIME_RANGES.map((r, i) => (
          <button key={r.label} className={`btn ${rangeIdx === i ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '6px 16px' }} onClick={() => setRangeIdx(i)}>
            {r.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading"><div className="spinner" />{t.trend.loading}</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            {SIGNALS.map(sig => {
              const d = data[sig.key] || [];
              const st = stats[sig.key];
              return (
                <div key={sig.key} className="card">
                  <p style={{ fontWeight: 600, color: 'var(--navy)', marginBottom: 4 }}>
                    {sig.label} ({TIME_RANGES[rangeIdx].label})
                  </p>
                  {st && (
                    <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
                      {t.trend.avg}: {st.avg} {sig.unit} &nbsp;|&nbsp; {t.trend.min}: {st.min} &nbsp;|&nbsp; {t.trend.max}: {st.max}
                    </p>
                  )}
                  {d.length === 0 ? (
                    <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                      {t.trend.noData}
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={140}>
                      <LineChart data={d} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="t" hide />
                        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11 }} />
                        <Tooltip formatter={v => [`${parseFloat(v).toFixed(1)} ${sig.unit}`, sig.label]}
                          labelFormatter={() => ''} contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                        <ReferenceLine y={sig.refMin} stroke="var(--danger)" strokeDasharray="4 2" strokeWidth={1} />
                        <ReferenceLine y={sig.refMax} stroke="var(--danger)" strokeDasharray="4 2" strokeWidth={1} />
                        <Line type="monotone" dataKey="val" stroke={sig.color} strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              );
            })}
          </div>

          <div className="card">
            <p style={{ fontWeight: 600, color: 'var(--navy)', marginBottom: 12 }}>
              {TIME_RANGES[rangeIdx].label} {t.trend.summary}
            </p>
            {Object.entries(stats).map(([key, st]) => {
              const sig = SIGNALS.find(s => s.key === key);
              return (
                <p key={key} style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>
                  • <strong>{sig?.label}:</strong> {t.trend.avg} {st.avg} {sig?.unit} &nbsp;|&nbsp; {t.trend.min} {st.min} &nbsp;|&nbsp; {t.trend.max} {st.max}
                </p>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}