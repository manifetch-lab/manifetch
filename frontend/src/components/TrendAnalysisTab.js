import { useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { api } from '../api/client';
import { useLang } from '../context/LanguageContext';

// GA bazlı referans değerleri
const GA_REF = {
  '24-29': { HEART_RATE: { min: 120, max: 177 }, SPO2: { min: 88, max: 98 }, RESP_RATE: { min: 30, max: 75 } },
  '29-33': { HEART_RATE: { min: 122, max: 175 }, SPO2: { min: 89, max: 98 }, RESP_RATE: { min: 30, max: 70 } },
  '33-37': { HEART_RATE: { min: 115, max: 172 }, SPO2: { min: 90, max: 99 }, RESP_RATE: { min: 30, max: 68 } },
  '37-43': { HEART_RATE: { min: 100, max: 160 }, SPO2: { min: 92, max: 100 }, RESP_RATE: { min: 30, max: 65 } },
};

function getRef(ga, key) {
  if (!ga) return { min: null, max: null };
  const bucket = ga < 29 ? '24-29' : ga < 33 ? '29-33' : ga < 37 ? '33-37' : '37-43';
  return GA_REF[bucket]?.[key] || { min: null, max: null };
}

export default function TrendAnalysisTab({ patientId, patient }) {
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

  // RR eklendi — 3 sinyal türü
  const SIGNALS = [
    { key: 'HEART_RATE', label: t.trend.heartRateTrend, unit: 'bpm',  color: '#1a9b8c' },
    { key: 'SPO2',       label: t.trend.spo2Trend,      unit: '%',    color: '#1e6eb5' },
    { key: 'RESP_RATE',  label: t.trend.respRateTrend, unit: '/min', color: '#7c3aed' },
  ];

  const ga = patient?.gestational_age_weeks;

  useEffect(() => {
    setLoading(true);
    const hours = TIME_RANGES[rangeIdx].hours;

    Promise.all(SIGNALS.map(s => api.getTrends(patientId, s.key, hours)))
      .then(results => {
        const newData  = {};
        const newStats = {};

        SIGNALS.forEach((s, i) => {
          const rows = results[i].data;
          // Veri fazlaysa örnekle — max 300 nokta
          const step = Math.max(1, Math.floor(rows.length / 300));
          newData[s.key] = rows
            .filter((_, idx) => idx % step === 0)
            .map(r => ({ t: r.timestamp_sec, val: r.value }));

          if (rows.length > 0) {
            const vals = rows.map(r => r.value);
            newStats[s.key] = {
              avg: (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1),
              min: Math.min(...vals).toFixed(1),
              max: Math.max(...vals).toFixed(1),
            };
          }
        });

        setData(newData);
        setStats(newStats);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [patientId, rangeIdx]);

  return (
    <div>
      {/* Zaman aralığı seçici */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-muted)' }}>
          {t.trend.timeRange}
        </span>
        {TIME_RANGES.map((r, i) => (
          <button
            key={r.label}
            className={`btn ${rangeIdx === i ? 'btn-primary' : 'btn-outline'}`}
            style={{ padding: '6px 16px' }}
            onClick={() => setRangeIdx(i)}
          >
            {r.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading"><div className="spinner" />{t.trend.loading}</div>
      ) : (
        <>
          {/* DÜZELTME: 3 grafik — HR, SpO2, RR */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
            {SIGNALS.map(sig => {
              const d   = data[sig.key] || [];
              const st  = stats[sig.key];
              const ref = getRef(ga, sig.key);   // GA bazlı referans çizgileri

              return (
                <div key={sig.key} className="card">
                  <p style={{ fontWeight: 600, color: 'var(--navy)', marginBottom: 4 }}>
                    {sig.label} ({TIME_RANGES[rangeIdx].label})
                  </p>
                  {st && (
                    <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
                      {t.trend.avg}: {st.avg} {sig.unit} &nbsp;|&nbsp;
                      {t.trend.min}: {st.min} &nbsp;|&nbsp;
                      {t.trend.max}: {st.max}
                    </p>
                  )}
                  {d.length === 0 ? (
                    <div style={{
                      height: 140, display: 'flex', alignItems: 'center',
                      justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13,
                    }}>
                      {t.trend.noData}
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={140}>
                      <LineChart data={d} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="t" hide />
                        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11 }} />
                        <Tooltip
                          formatter={v => [`${parseFloat(v).toFixed(1)} ${sig.unit}`, sig.label]}
                          labelFormatter={() => ''}
                          contentStyle={{ fontSize: 12, borderRadius: 6 }}
                        />
                        {/* DÜZELTME: GA bazlı referans çizgileri */}
                        {ref.min !== null && (
                          <ReferenceLine y={ref.min} stroke="var(--danger)"
                            strokeDasharray="4 2" strokeWidth={1} />
                        )}
                        {ref.max !== null && (
                          <ReferenceLine y={ref.max} stroke="var(--danger)"
                            strokeDasharray="4 2" strokeWidth={1} />
                        )}
                        <Line
                          type="monotone" dataKey="val"
                          stroke={sig.color} strokeWidth={1.5} dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              );
            })}
          </div>

          {/* Özet istatistikler */}
          <div className="card">
            <p style={{ fontWeight: 600, color: 'var(--navy)', marginBottom: 12 }}>
              {TIME_RANGES[rangeIdx].label} {t.trend.summary}
            </p>
            {Object.entries(stats).map(([key, st]) => {
              const sig = SIGNALS.find(s => s.key === key);
              const ref = getRef(ga, key);
              return (
                <p key={key} style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>
                  • <strong>{sig?.label}:</strong>&nbsp;
                  {t.trend.avg} {st.avg} {sig?.unit} &nbsp;|&nbsp;
                  {t.trend.min} {st.min} &nbsp;|&nbsp;
                  {t.trend.max} {st.max}
                  {ref.min !== null && (
                    <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                      &nbsp; ({t.trend.reference}: {ref.min}–{ref.max})
                    </span>
                  )}
                </p>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}