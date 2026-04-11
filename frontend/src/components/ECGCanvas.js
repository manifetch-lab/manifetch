import { useEffect, useRef, useState } from 'react';

const WS_BASE     = (process.env.REACT_APP_WS_URL || 'ws://127.0.0.1:8000');
const ECG_HZ      = 25;
const DISPLAY_SEC = 6;
const BUFFER_SIZE = ECG_HZ * DISPLAY_SEC;

export default function ECGCanvas({ patientId }) {
  const canvasRef = useRef(null);
  const bufferRef = useRef([]);
  const wsRef     = useRef(null);
  const animRef   = useRef(null);
  const [wsState, setWsState] = useState('connecting');

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      const token = sessionStorage.getItem('token');
      if (!token || cancelled) { setWsState('error'); return; }

      const ws = new WebSocket(`${WS_BASE}/ws/ecg/${patientId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ token }));
        setWsState('connected');
      };

      ws.onclose = () => {
        setWsState('disconnected');
        if (!cancelled) {
          setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => setWsState('error');

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'ecg' && Array.isArray(msg.samples)) {
          bufferRef.current.push(...msg.samples);
          if (bufferRef.current.length > BUFFER_SIZE)
            bufferRef.current = bufferRef.current.slice(-BUFFER_SIZE);
        }
      };
    };

    setWsState('connecting');
    connect();

    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN)
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
    }, 25000);

    return () => {
      cancelled = true;
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [patientId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const draw = () => {
      const W = canvas.width;
      const H = canvas.height;
      const data = bufferRef.current;

      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, W, H);

      ctx.strokeStyle = 'rgba(0,200,100,0.08)';
      ctx.lineWidth = 0.5;
      for (let x = 0; x <= W; x += W / 12) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      }
      for (let y = 0; y <= H; y += H / 6) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      }

      if (data.length < 2) {
        ctx.fillStyle = 'rgba(0,200,100,0.4)';
        ctx.font = '12px DM Mono, monospace';
        ctx.textAlign = 'center';
        ctx.fillText(
          wsState === 'connected' ? 'ECG sinyali bekleniyor...' : 'ECG bağlantısı kuruluyor...',
          W / 2, H / 2
        );
        animRef.current = requestAnimationFrame(draw);
        return;
      }

      const min = Math.min(...data);
      const max = Math.max(...data);
      const range = max - min || 1;
      const pad = H * 0.1;

      ctx.beginPath();
      ctx.strokeStyle = '#00c864';
      ctx.lineWidth = 1.5;
      ctx.shadowColor = '#00c864';
      ctx.shadowBlur = 4;
      data.forEach((val, i) => {
        const x = (i / (BUFFER_SIZE - 1)) * W;
        const y = pad + ((max - val) / range) * (H - 2 * pad);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.fillStyle = 'rgba(0,200,100,0.5)';
      ctx.font = '10px DM Mono, monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`${DISPLAY_SEC}s | ${ECG_HZ}Hz`, W - 6, H - 4);

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [wsState]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        canvas.width  = e.contentRect.width;
        canvas.height = e.contentRect.height;
      }
    });
    ro.observe(canvas.parentElement);
    return () => ro.disconnect();
  }, []);

  const statusColor = wsState === 'connected' ? '#00c864' : wsState === 'connecting' ? '#f59e0b' : '#e53935';
  const statusLabel = wsState === 'connected' ? 'ECG Canlı' : wsState === 'connecting' ? 'Bağlanıyor...' : 'Bağlantı Yok';

  return (
    <div>
      <div style={{ background: '#0a0a0a', borderRadius: 8, overflow: 'hidden', height: 140 }}>
        <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor, display: 'inline-block' }} />
        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'DM Mono, monospace' }}>
          {statusLabel}
        </span>
      </div>
    </div>
  );
}