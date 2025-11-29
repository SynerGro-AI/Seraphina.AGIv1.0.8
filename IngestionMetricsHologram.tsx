import React, { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Brush,
  ReferenceArea,
  ReferenceLine,
} from 'recharts';

interface Metrics {
  totalAdded: number;
  totalFailed: number;
  retries: number;
  lastIngestTs: number | null;
  encryption: string;
  decryptFailures: number;
}

const useThemeMode = () => {
  const [mode, setMode] = useState<'dark' | 'light'>(
    () => (typeof document !== 'undefined' && document.documentElement.classList.contains('light')) ? 'light' : 'dark'
  );
  useEffect(() => {
    const obs = new MutationObserver(() => {
      setMode(document.documentElement.classList.contains('light') ? 'light' : 'dark');
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);
  return mode;
};

export const IngestionMetricsHologram: React.FC = () => {
  const theme = useThemeMode();
  const { data: metricsResp, error } = useQuery({
    queryKey: ['ingestMetrics'],
    queryFn: async () => {
      const res = await fetch('/api/ingest/metrics');
      const json = await res.json();
      if (!json.available) throw new Error(json.reason || json.error || 'unavailable');
      return json as Metrics;
    },
    refetchInterval: 5000,
    staleTime: 4000,
  });
  const metrics = metricsResp || null;

  const [history, setHistory] = useState<number[]>(() => {
    if (typeof window !== 'undefined') {
      try {
        const raw = sessionStorage.getItem('ingestHistory');
        if (raw) return (JSON.parse(raw) as number[]).slice(-60);
      } catch {}
    }
    return [];
  });
  useEffect(() => {
    if (!metrics) return;
    const total = metrics.totalAdded + metrics.totalFailed;
    const rate = total > 0 ? metrics.totalAdded / total : 0;
    setHistory((h) => {
      const next = [...h, rate];
      while (next.length > 60) next.shift();
      try { sessionStorage.setItem('ingestHistory', JSON.stringify(next)); } catch {}
      return next;
    });
  }, [metrics?.totalAdded, metrics?.totalFailed]);

  const animValuesRef = useRef<Record<string, number>>({});
  const targetValuesRef = useRef<Record<string, number>>({});
  const rafSpring = useRef<number>();
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!metrics) return;
    const numeric: Record<string, number> = {
      totalAdded: metrics.totalAdded,
      totalFailed: metrics.totalFailed,
      retries: metrics.retries,
      decryptFailures: metrics.decryptFailures,
      successRate: metrics.totalAdded + metrics.totalFailed > 0 ? (metrics.totalAdded / (metrics.totalAdded + metrics.totalFailed)) * 100 : 0,
    };
    Object.entries(numeric).forEach(([k, v]) => {
      if (animValuesRef.current[k] === undefined) animValuesRef.current[k] = v;
      targetValuesRef.current[k] = v;
    });
    const prefersReduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) {
      Object.entries(targetValuesRef.current).forEach(([k, v]) => (animValuesRef.current[k] = v));
      forceTick((n) => n + 1);
      return;
    }
    const step = () => {
      let cont = false;
      for (const [k, target] of Object.entries(targetValuesRef.current)) {
        const cur = animValuesRef.current[k];
        const next = cur + (target - cur) * 0.18;
        if (Math.abs(next - target) > 0.02) {
          animValuesRef.current[k] = next;
          cont = true;
        } else {
          animValuesRef.current[k] = target;
        }
      }
      forceTick((n) => n + 1);
      if (cont) rafSpring.current = requestAnimationFrame(step);
    };
    if (rafSpring.current) cancelAnimationFrame(rafSpring.current);
    rafSpring.current = requestAnimationFrame(step);
    return () => { if (rafSpring.current) cancelAnimationFrame(rafSpring.current); };
  }, [metrics?.totalAdded, metrics?.totalFailed, metrics?.retries, metrics?.decryptFailures]);
  const animated = animValuesRef.current;

  useEffect(() => {
    if (!metrics) return;
    try {
      const key = 'ingestMetricsHistorySnapshots';
      const existingRaw = localStorage.getItem(key);
      let arr: any[] = [];
      if (existingRaw) {
        try { arr = JSON.parse(existingRaw); } catch { arr = []; }
      }
      arr.push({ ts: Date.now(), ...metrics });
      if (arr.length > 500) arr.splice(0, arr.length - 500);
      localStorage.setItem(key, JSON.stringify(arr));
    } catch {}
  }, [metrics?.totalAdded, metrics?.totalFailed, metrics?.retries, metrics?.decryptFailures]);

  function exportSnapshots(format: 'json' | 'csv') {
    try {
      const key = 'ingestMetricsHistorySnapshots';
      const raw = localStorage.getItem(key);
      if (!raw) return;
      const arr = JSON.parse(raw);
      let blob: Blob;
      let file = `ingestion-metrics.${format}`;
      if (format === 'json') {
        blob = new Blob([JSON.stringify(arr, null, 2)], { type: 'application/json' });
      } else {
        const headers = ['ts', 'totalAdded', 'totalFailed', 'retries', 'lastIngestTs', 'encryption', 'decryptFailures'];
        const lines = [headers.join(',')];
        arr.forEach((r: any) => {
          lines.push(headers.map((h) => JSON.stringify(r[h] ?? '')).join(','));
        });
        blob = new Blob([lines.join('\n')], { type: 'text/csv' });
        file = 'ingestion-metrics.csv';
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(url);
        a.remove();
      }, 1000);
    } catch {}
  }

  function exportAnomalies(format: 'json' | 'csv') {
    if (!stats) return;
    try {
      const rows: any[] = [];
      [...stats.anomalyIdx.values()].forEach((i) => {
        const base = chartData[i];
        if (!base) return;
        const successRate = (base.totalAdded + base.totalFailed) > 0 ? (base.totalAdded / (base.totalAdded + base.totalFailed)) * 100 : 0;
        rows.push({
          index: i,
          ts: base.ts,
          time: new Date(base.ts).toISOString(),
          totalAdded: base.totalAdded,
          totalFailed: base.totalFailed,
          retries: base.retries,
          decryptFailures: base.decryptFailures,
          successRate: Number(successRate.toFixed(2)),
          reasons: stats.reasons?.[i]?.join('|') || '',
        });
      });
      if (!rows.length) return;
      if (format === 'json') {
        const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'ingestion-anomalies.json';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          URL.revokeObjectURL(url);
          a.remove();
        }, 1000);
      } else {
        const headers = ['index', 'ts', 'time', 'totalAdded', 'totalFailed', 'retries', 'decryptFailures', 'successRate', 'reasons'];
        const lines = [headers.join(',')];
        rows.forEach((r) => lines.push(headers.map((h) => JSON.stringify(r[h] ?? '')).join(',')));
        const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'ingestion-anomalies.csv';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          URL.revokeObjectURL(url);
          a.remove();
        }, 1000);
      }
    } catch {}
  }

  const [seriesEnabled, setSeriesEnabled] = useState<Record<string, boolean>>({
    totalAdded: true,
    totalFailed: true,
    retries: false,
    decryptFailures: false,
    successRate: true,
  });
  const toggleSeries = (k: string) => {
    setSeriesEnabled((s) => ({ ...s, [k]: !s[k] }));
  };

  const [chartData, setChartData] = useState<any[]>([]);
  const [smoothWindow, setSmoothWindow] = useState<number>(1);
  const smoothingOptions = [1, 5, 10, 20];
  useEffect(() => {
    try {
      const raw = localStorage.getItem('ingestMetricsHistorySnapshots');
      if (!raw) return;
      const arr: any[] = JSON.parse(raw).slice(-500);
      setChartData(
        arr.map((s) => ({
          ...s,
          successRate: (s.totalAdded + s.totalFailed) > 0 ? (s.totalAdded / (s.totalAdded + s.totalFailed)) * 100 : 0,
          time: new Date(s.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        }))
      );
    } catch {}
  }, [metrics?.totalAdded, metrics?.totalFailed, metrics?.retries, metrics?.decryptFailures]);

  const smoothedData = React.useMemo(() => {
    if (smoothWindow <= 1) return chartData;
    const keys = ['totalAdded', 'totalFailed', 'retries', 'decryptFailures', 'successRate'] as const;
    const out: any[] = [];
    for (let i = 0; i < chartData.length; i++) {
      const start = Math.max(0, i - smoothWindow + 1);
      const slice = chartData.slice(start, i + 1);
      const agg: any = { ...chartData[i] };
      keys.forEach((k) => {
        let sum = 0;
        slice.forEach((r) => (sum += r[k] || 0));
        agg[k] = sum / slice.length;
      });
      out.push(agg);
    }
    return out;
  }, [chartData, smoothWindow]);

  const [percentiles, setPercentiles] = useState<{ low: number; high: number }>(() => {
    if (typeof localStorage !== 'undefined') {
      try {
        const raw = localStorage.getItem('ingestPctBounds');
        if (raw) return JSON.parse(raw);
      } catch {}
    }
    return { low: 10, high: 90 };
  });
  useEffect(() => {
    try { localStorage.setItem('ingestPctBounds', JSON.stringify(percentiles)); } catch {}
  }, [percentiles.low, percentiles.high]);
  const stats = React.useMemo(() => {
    if (!chartData.length) return null;
    const successArr = chartData.map((d) =>
      (d.totalAdded + d.totalFailed) > 0 ? (d.totalAdded / (d.totalAdded + d.totalFailed)) * 100 : 0
    );
    function pct(arr: number[], p: number) {
      if (!arr.length) return 0;
      const sorted = [...arr].sort((a, b) => a - b);
      const idx = (p / 100) * (sorted.length - 1);
      const lo = Math.floor(idx);
      const hi = Math.ceil(idx);
      if (lo === hi) return sorted[lo];
      const t = idx - lo;
      return sorted[lo] * (1 - t) + sorted[hi] * t;
    }
    const p10 = pct(successArr, percentiles.low);
    const p90 = pct(successArr, percentiles.high);
    const deltasFailed: number[] = [];
    for (let i = 1; i < chartData.length; i++) {
      const prev = chartData[i - 1];
      const cur = chartData[i];
      const delta = Math.max(0, cur.totalFailed - prev.totalFailed);
      deltasFailed.push(delta);
    }
    const mean = deltasFailed.reduce((a, b) => a + b, 0) / (deltasFailed.length || 1);
    const variance = deltasFailed.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (deltasFailed.length || 1);
    const std = Math.sqrt(variance);
    const spikeThreshold = mean + 2 * std;
    const anomalyIdx = new Set<number>();
    const reasons: Record<number, string[]> = {};
    for (let i = 0; i < successArr.length; i++) {
      const rate = successArr[i];
      if (rate < p10) {
        anomalyIdx.add(i);
        (reasons[i] ||= []).push('lowSuccess');
      } else if (rate > p90) {
        anomalyIdx.add(i);
        (reasons[i] ||= []).push('highSuccess');
      }
      if (i > 0) {
        const deltaF = Math.max(0, chartData[i].totalFailed - chartData[i - 1].totalFailed);
        if (deltaF > spikeThreshold && deltaF > 0) {
          anomalyIdx.add(i);
          (reasons[i] ||= []).push(`failureSpike(${deltaF})`);
        }
      }
    }
    return { p10, p90, anomalyIdx, spikeThreshold, count: successArr.length, reasons };
  }, [chartData, percentiles.low, percentiles.high]);

  const lastPushedRef = useRef<number>(0);
  const pushInFlightRef = useRef(false);
  useEffect(() => {
    if (!stats || !stats.anomalyIdx.size) return;
    const anomalyCount = stats.anomalyIdx.size;
    if (anomalyCount === lastPushedRef.current) return;
    if (pushInFlightRef.current) return;
    pushInFlightRef.current = true;
    const anomaliesPayload = [...stats.anomalyIdx.values()].map((i) => {
      const base = chartData[i];
      if (!base) return null;
      const successRate = (base.totalAdded + base.totalFailed) > 0 ? (base.totalAdded / (base.totalAdded + base.totalFailed)) * 100 : 0;
      return {
        index: i,
        ts: base.ts,
        totalAdded: base.totalAdded,
        totalFailed: base.totalFailed,
        retries: base.retries,
        decryptFailures: base.decryptFailures,
        successRate: Number(successRate.toFixed(2)),
        reasons: stats.reasons?.[i] || [],
      };
    }).filter(Boolean);
    setTimeout(() => {
      const payload = { anomalies: anomaliesPayload, meta: { source: 'renderer', version: 1 } };
      const queueKey = 'anomalyOutboundQueue';
      fetch('/api/ingest/anomalies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then((r) => {
          if (!r.ok) throw new Error('bad');
          return r.json();
        })
        .then(() => {
          lastPushedRef.current = anomalyCount;
        })
        .catch(() => {
          try {
            const existing = JSON.parse(localStorage.getItem(queueKey) || '[]');
            existing.push(payload);
            localStorage.setItem(queueKey, JSON.stringify(existing.slice(-200)));
          } catch {}
        })
        .finally(() => {
          pushInFlightRef.current = false;
        });
    }, 600);
  }, [stats?.anomalyIdx.size]);

  const retryDelayRef = useRef<number>(5000);
  useEffect(() => {
    const queueKey = 'anomalyOutboundQueue';
    let timer: any;
    const flush = () => {
      if (document.hidden) {
        schedule();
        return;
      }
      try {
        const arr = JSON.parse(localStorage.getItem(queueKey) || '[]');
        if (!arr.length) {
          retryDelayRef.current = 5000;
          schedule();
          return;
        }
        const next = arr.shift();
        fetch('/api/ingest/anomalies', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(next),
        })
          .then((r) => {
            if (!r.ok) throw new Error('bad');
            return r.json();
          })
          .then(() => {
            localStorage.setItem(queueKey, JSON.stringify(arr));
            retryDelayRef.current = 5000;
          })
          .catch(() => {
            retryDelayRef.current = Math.min(retryDelayRef.current * 1.8 + Math.random() * 400, 90_000);
          })
          .finally(schedule);
      } catch {
        retryDelayRef.current = Math.min(retryDelayRef.current * 1.8, 60_000);
        schedule();
      }
    };
    const schedule = () => {
      timer = setTimeout(flush, retryDelayRef.current);
    };
    schedule();
    window.addEventListener('online', flush);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('online', flush);
    };
  }, []);

  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource('/api/ingest/anomalies/feed');
      es.addEventListener('anomalies', (ev: MessageEvent) => {
        try {
          const payload = JSON.parse(ev.data);
          if (Array.isArray(payload.anomalies)) {
            setChartData((d) => {
              const existingTs = new Set(d.map((x) => x.ts));
              const add: any[] = [];
              payload.anomalies.forEach((a: any) => {
                if (!existingTs.has(a.ts)) {
                  add.push({
                    ts: a.ts,
                    totalAdded: a.totalAdded ?? 0,
                    totalFailed: a.totalFailed ?? 0,
                    retries: a.retries ?? 0,
                    decryptFailures: a.decryptFailures ?? 0,
                    successRate: a.successRate ?? 0,
                    time: new Date(a.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
                  });
                }
              });
              return [...d, ...add].slice(-500);
            });
          }
        } catch {}
      });
    } catch {}
    return () => {
      try { es?.close(); } catch {}
    };
  }, []);

  const AnomalyDot = (props: any) => {
    if (!stats) return null;
    const idx = props.index as number;
    if (!stats.anomalyIdx.has(idx)) return null;
    const reasons = stats.reasons[idx] || [];
    const spike = reasons.some((r) => r.startsWith('failureSpike'));
    const low = reasons.includes('lowSuccess');
    const high = reasons.includes('highSuccess');
    let fill = '#ff4d6d';
    if (spike) fill = '#ffb347';
    else if (low) fill = '#e63946';
    else if (high) fill = '#10b981';
    return (
      <g>
        <circle cx={props.cx} cy={props.cy} r={5} fill={fill} stroke="#fff" strokeWidth={1.5} />
        <circle cx={props.cx} cy={props.cy} r={8} fill={fill === '#10b981' ? 'rgba(16,185,129,0.25)' : 'rgba(255,77,109,0.25)'} />
      </g>
    );
  };

  function handleSkip(e: React.MouseEvent) {
    e.preventDefault();
    const target = document.querySelector('[data-main-focus-target]') as HTMLElement | null;
    if (target) target.focus();
    else window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  const sparkRef = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = sparkRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const w = (canvas.width = canvas.clientWidth * (window.devicePixelRatio || 1));
    const h = (canvas.height = canvas.clientHeight * (window.devicePixelRatio || 1));
    ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
    ctx.clearRect(0, 0, w, h);
    if (!history.length) return;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, '#0ff');
    grad.addColorStop(1, '#0fa');
    ctx.strokeStyle = grad;
    const max = 1;
    const min = 0;
    const span = Math.max(1, history.length - 1);
    ctx.beginPath();
    history.forEach((v, i) => {
      const x = (i / span) * (canvas.clientWidth - 4) + 2;
      const y = (1 - (v - min) / (max - min)) * (canvas.clientHeight - 4) + 2;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.lineTo(canvas.clientWidth, canvas.clientHeight);
    ctx.lineTo(0, canvas.clientHeight);
    ctx.closePath();
    const fillGrad = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight);
    fillGrad.addColorStop(0, 'rgba(0,255,200,0.25)');
    fillGrad.addColorStop(1, 'rgba(0,255,200,0)');
    ctx.fillStyle = fillGrad;
    ctx.fill();
  }, [history, theme]);

  const particleRef = useRef<HTMLCanvasElement | null>(null);
  const activeRef = useRef(true);
  useEffect(() => {
    const onBlur = () => { activeRef.current = false; };
    const onFocus = () => { activeRef.current = true; };
    const onVis = () => { activeRef.current = document.visibilityState === 'visible'; };
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);
  useEffect(() => {
    const canvas = particleRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let raf: number | undefined;
    interface Particle {
      x: number;
      y: number;
      r: number;
      v: number;
    }
    const particles: Particle[] = Array.from({ length: 24 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 2 + 0.5,
      v: Math.random() * 0.0006 + 0.0002,
    }));
    function loop() {
      if (!canvas || !ctx) return;
      const rate = history.length ? history[history.length - 1] : 0;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      if (activeRef.current) {
        particles.forEach((p) => {
          p.y -= p.v * (0.5 + rate);
          if (p.y < -0.05) {
            p.y = 1.05;
            p.x = Math.random();
          }
          const gx = p.x * w;
          const gy = p.y * h;
          const alpha = Math.min(1, 0.15 + rate * 0.7);
          ctx.beginPath();
          ctx.arc(gx, gy, p.r + rate * 1.2, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${rate > 0.7 ? 0 : 0}, ${rate > 0.7 ? 255 : 180}, 255, ${alpha})`;
          ctx.fill();
        });
      }
      raf = requestAnimationFrame(loop);
    }
    loop();
    return () => { if (raf) cancelAnimationFrame(raf); };
  }, [history]);

  const small = typeof window !== 'undefined' ? window.innerWidth < 900 : false;
  const palette = theme === 'light'
    ? {
        text: '#034',
        accent: '#067',
        panelBg: 'rgba(255,255,255,0.55)',
        border: 'rgba(0,120,170,0.35)',
        heading: '#024',
        fail: '#a0264c',
      }
    : {
        text: '#cfe',
        accent: '#0ff',
        panelBg: 'linear-gradient(135deg, rgba(20,40,60,0.55), rgba(10,15,25,0.65))',
        border: 'rgba(0,180,255,0.25)',
        heading: '#aff',
        fail: '#ff4d6d',
      };

  const baseStyle: React.CSSProperties = {
    position: 'relative',
    width: '100%',
    maxWidth: small ? 340 : 460,
    padding: small ? '14px 16px 20px' : '18px 22px 26px',
    borderRadius: small ? 14 : 18,
    background: palette.panelBg,
    boxShadow: '0 0 24px -4px rgba(0,200,255,0.28), inset 0 0 30px -12px rgba(0,150,255,0.25)',
    backdropFilter: 'blur(14px)',
    WebkitBackdropFilter: 'blur(14px)',
    overflow: 'hidden',
  };

  const glow = (color: string, size = small ? 180 : 300, blur = small ? 90 : 140) => ({
    position: 'absolute' as const,
    top: '50%',
    left: '50%',
    width: size,
    height: size,
    background: `radial-gradient(circle, ${color}, transparent 70%)`,
    filter: `blur(${blur}px)`,
    transform: 'translate(-50%, -50%)',
    opacity: 0.35,
    pointerEvents: 'none',
  });

  const now = Date.now();
  const ageSec = metrics?.lastIngestTs ? (now - metrics.lastIngestTs) / 1000 : 0;
  const successRate = metrics ? (metrics.totalAdded + metrics.totalFailed > 0 ? (metrics.totalAdded / (metrics.totalAdded + metrics.totalFailed)) * 100 : 0) : 0;

  return (
    <div style={{ position: 'relative' }}>
      <a
        href="#"
        onClick={handleSkip}
        style={{
          position: 'absolute',
          left: 8,
          top: -40,
          background: '#0af',
          color: '#012',
          padding: '6px 10px',
          borderRadius: 6,
          fontSize: 12,
          textDecoration: 'none',
          transform: 'translateY(0)',
          transition: 'top .25s',
          zIndex: 1000,
        }}
        onFocus={(e) => (e.currentTarget.style.top = '8px')}
        onBlur={(e) => (e.currentTarget.style.top = '-40px')}
      >
        Skip telemetry
      </a>
      <div style={baseStyle} role="region" aria-label="Ingestion telemetry" tabIndex={-1}>
        <div style={{ position: 'absolute', inset: 0, border: `1px solid ${palette.border}`, borderRadius: baseStyle.borderRadius as number, pointerEvents: 'none' }} />
        <div style={glow('rgba(0,160,255,0.8)')} />
        <div style={glow('rgba(0,255,180,0.9)', small ? 120 : 180, small ? 60 : 90)} />
        <div style={{ position: 'relative' }}>
          <h3
            style={{
              margin: 0,
              fontSize: small ? 16 : 18,
              fontWeight: 600,
              letterSpacing: 1,
              color: palette.heading,
              textShadow: theme === 'dark' ? '0 0 8px rgba(0,200,255,0.6)' : 'none',
            }}
          >
            Ingestion Telemetry
          </h3>
          {!metrics && !error && (
            <div style={{ marginTop: 12, color: palette.text, opacity: 0.65 }} role="status" aria-live="polite">
              Initializing secure channel...
            </div>
          )}
          {error && (
            <div style={{ marginTop: 12, color: palette.fail, fontSize: 12 }} role="alert">
              Unavailable: {(error as Error).message}
            </div>
          )}
          {metrics && (
            <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: small ? '1fr 1fr' : 'repeat(2, minmax(0, 1fr))', gap: small ? 10 : 14 }}>
              {[
                { label: 'Total Added', value: animated.totalAdded ?? metrics.totalAdded, hue: 180, desc: 'Files successfully ingested and stored.' },
                { label: 'Total Failed', value: animated.totalFailed ?? metrics.totalFailed, hue: 350, desc: 'Files that failed after all retry attempts.' },
                { label: 'Retries', value: animated.retries ?? metrics.retries, hue: 45, desc: 'Total retry batch cycles executed.' },
                { label: 'Decrypt Fails', value: animated.decryptFailures ?? metrics.decryptFailures, hue: 300, desc: 'Failed attempts to decrypt stored metadata.' },
              ].map((cell) => (
                <div
                  key={cell.label}
                  tabIndex={0}
                  title={cell.desc}
                  style={{
                    position: 'relative',
                    padding: small ? '10px 8px 12px' : '12px 10px 14px',
                    borderRadius: 12,
                    background: theme === 'dark' ? 'rgba(0,20,35,0.35)' : 'rgba(255,255,255,0.4)',
                    boxShadow: '0 0 0 1px rgba(0,140,255,0.25), 0 0 14px -4px rgba(0,180,255,0.35) inset',
                    outline: 'none',
                  }}
                  onFocus={(e) =>
                    (e.currentTarget.style.boxShadow = '0 0 0 2px #0ff, 0 0 14px -4px rgba(0,255,255,0.6) inset')
                  }
                  onBlur={(e) =>
                    (e.currentTarget.style.boxShadow = '0 0 0 1px rgba(0,140,255,0.25), 0 0 14px -4px rgba(0,180,255,0.35) inset')
                  }
                  aria-label={`${cell.label}: ${Math.round(cell.value)}. ${cell.desc}`}
                >
                  <div
                    style={{
                      fontSize: 11,
                      letterSpacing: 1,
                      textTransform: 'uppercase',
                      opacity: 0.7,
                      color: `hsl(${cell.hue}, 70%, ${theme === 'dark' ? 70 : 35}%)`,
                    }}
                  >
                    {cell.label}
                  </div>
                  <div
                    style={{
                      fontSize: small ? 20 : 24,
                      fontWeight: 600,
                      color: `hsl(${cell.hue}, 85%, ${theme === 'dark' ? 75 : 35}%)`,
                      textShadow: theme === 'dark' ? `0 0 10px hsl(${cell.hue}, 85%, 60%)` : 'none',
                    }}
                    aria-live="polite"
                    aria-label={`${cell.label} ${Math.round(cell.value)}`}
                  >
                    {Math.round(cell.value)}
                  </div>
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background: `radial-gradient(circle at 65% 30%, hsla(${cell.hue}, 90%, 55%, 0.25), transparent)`,
                      mixBlendMode: theme === 'dark' ? 'screen' : 'normal',
                      pointerEvents: 'none',
                    }}
                  />
                </div>
              ))}
            </div>
          )}
          {metrics && (
            <div style={{ marginTop: 18, fontSize: 12, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              <Stat label="Encryption" value={metrics.encryption} theme={theme} />
              <Stat label="Last Ingest" value={metrics.lastIngestTs ? (ageSec < 60 ? `${ageSec.toFixed(0)}s ago` : `${Math.round(ageSec / 60)}m ago`) : '—'} theme={theme} />
              <Stat
                label="Success Rate"
                value={
                  animated.successRate !== undefined
                    ? `${animated.successRate.toFixed(1)}%`
                    : metrics.totalAdded + metrics.totalFailed > 0
                    ? `${successRate.toFixed(1)}%`
                    : '—'
                }
                theme={theme}
              />
            </div>
          )}
          {metrics && (
            <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => exportSnapshots('json')}
                style={{ background: '#044', color: '#0ff', border: '1px solid #0aa', padding: '6px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer' }}
                aria-label="Export metrics as JSON"
              >
                JSON
              </button>
              <button
                type="button"
                onClick={() => exportSnapshots('csv')}
                style={{ background: '#044', color: '#0ff', border: '1px solid #0aa', padding: '6px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer' }}
                aria-label="Export metrics as CSV"
              >
                CSV
              </button>
              <button
                type="button"
                onClick={() => exportAnomalies('json')}
                disabled={!stats || !stats.anomalyIdx.size}
                style={{
                  background: !stats || !stats.anomalyIdx.size ? '#222' : '#400',
                  color: '#fdd',
                  border: '1px solid #f55',
                  padding: '6px 10px',
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: !stats || !stats.anomalyIdx.size ? 'not-allowed' : 'pointer',
                  opacity: !stats || !stats.anomalyIdx.size ? 0.4 : 1,
                }}
                aria-label="Export anomalies as JSON"
              >
                Anom JSON
              </button>
              <button
                type="button"
                onClick={() => exportAnomalies('csv')}
                disabled={!stats || !stats.anomalyIdx.size}
                style={{
                  background: !stats || !stats.anomalyIdx.size ? '#222' : '#400',
                  color: '#fdd',
                  border: '1px solid #f55',
                  padding: '6px 10px',
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: !stats || !stats.anomalyIdx.size ? 'not-allowed' : 'pointer',
                  opacity: !stats || !stats.anomalyIdx.size ? 0.4 : 1,
                }}
                aria-label="Export anomalies as CSV"
              >
                Anom CSV
              </button>
            </div>
          )}
          <div style={{ marginTop: 16, position: 'relative', height: 60 }} aria-label="Success rate sparkline" role="img">
            <canvas
              ref={sparkRef}
              style={{
                width: '100%',
                height: 40,
                display: 'block',
                borderRadius: 8,
                background: theme === 'dark' ? 'rgba(0,30,45,0.4)' : 'rgba(255,255,255,0.5)',
                boxShadow: '0 0 0 1px rgba(0,140,255,0.2), inset 0 0 12px -4px rgba(0,160,255,0.4)',
              }}
            />
            <canvas ref={particleRef} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} aria-hidden="true" />
          </div>
          <div style={{ marginTop: 24 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              {Object.entries(seriesEnabled).map(([k, v]) => (
                <button
                  key={k}
                  onClick={() => toggleSeries(k)}
                  aria-pressed={v}
                  aria-label={`Toggle ${k} series`}
                  style={{
                    background: v ? 'linear-gradient(90deg, #0ff, #0af)' : 'rgba(255,255,255,0.1)',
                    color: v ? '#012' : '#9fe',
                    border: '1px solid rgba(0,200,255,0.4)',
                    padding: '4px 10px',
                    borderRadius: 20,
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: 0.5,
                    cursor: 'pointer',
                    boxShadow: v ? '0 0 0 2px rgba(0,255,255,0.3), 0 0 10px -2px rgba(0,255,255,0.6)' : 'none',
                  }}
                  onFocus={(e) => (e.currentTarget.style.boxShadow = '0 0 0 2px #0ff, 0 0 10px -2px rgba(0,255,255,0.7)')}
                  onBlur={(e) =>
                    (e.currentTarget.style.boxShadow = v
                      ? '0 0 0 2px rgba(0,255,255,0.3), 0 0 10px -2px rgba(0,255,255,0.6)'
                      : 'none')
                  }
                >
                  {k}
                </button>
              ))}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 8 }}>
                <label style={{ fontSize: 11, letterSpacing: 0.5, opacity: 0.7 }}>Smoothing</label>
                <select
                  value={smoothWindow}
                  onChange={(e) => setSmoothWindow(Number(e.target.value))}
                  style={{
                    background: 'rgba(0,0,0,0.3)',
                    color: '#0ff',
                    border: '1px solid rgba(0,200,255,0.4)',
                    borderRadius: 6,
                    padding: '4px 6px',
                    fontSize: 11,
                  }}
                  aria-label="Select smoothing window"
                >
                  {smoothingOptions.map((o) => (
                    <option key={o} value={o}>
                      {o === 1 ? 'Off' : `${o} pt`}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <label style={{ fontSize: 11, letterSpacing: 0.5, opacity: 0.7 }}>Band</label>
                <input
                  type="number"
                  min={0}
                  max={percentiles.high - 1}
                  value={percentiles.low}
                  aria-label="Lower percentile"
                  onChange={(e) =>
                    setPercentiles((p) => ({ ...p, low: Math.min(Number(e.target.value), p.high - 1) }))
                  }
                  style={{
                    width: 52,
                    background: 'rgba(0,0,0,0.3)',
                    color: '#0ff',
                    border: '1px solid rgba(0,200,255,0.4)',
                    borderRadius: 6,
                    padding: '4px 4px',
                    fontSize: 11,
                  }}
                />
                <span style={{ fontSize: 11, opacity: 0.6 }}>/</span>
                <input
                  type="number"
                  min={percentiles.low + 1}
                  max={100}
                  value={percentiles.high}
                  aria-label="Upper percentile"
                  onChange={(e) =>
                    setPercentiles((p) => ({ ...p, high: Math.max(Number(e.target.value), p.low + 1) }))
                  }
                  style={{
                    width: 52,
                    background: 'rgba(0,0,0,0.3)',
                    color: '#0ff',
                    border: '1px solid rgba(0,200,255,0.4)',
                    borderRadius: 6,
                    padding: '4px 4px',
                    fontSize: 11,
                  }}
                />
              </div>
            </div>
            <div
              style={{
                width: '100%',
                height: 220,
                background: theme === 'dark' ? 'rgba(0,25,40,0.45)' : 'rgba(255,255,255,0.55)',
                border: '1px solid rgba(0,180,255,0.25)',
                borderRadius: 14,
                padding: '4px 4px 0 0',
              }}
            >
              {chartData.length < 2 && (
                <div style={{ padding: 12, fontSize: 12, color: '#cfe', opacity: 0.65 }}>Collecting samples for trend...</div>
              )}
              {chartData.length >= 2 && (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={smoothedData} margin={{ top: 8, right: 14, left: 4, bottom: 6 }}>
                    <CartesianGrid strokeDasharray="4 4" stroke="rgba(0,200,255,0.15)" />
                    <XAxis
                      dataKey="time"
                      tick={{ fill: theme === 'dark' ? '#9ff' : '#024', fontSize: 10 }}
                      stroke="rgba(0,200,255,0.25)"
                      interval={Math.max(0, Math.floor(chartData.length / 8))}
                    />
                    <YAxis
                      tick={{ fill: theme === 'dark' ? '#9ff' : '#024', fontSize: 10 }}
                      stroke="rgba(0,200,255,0.25)"
                      domain={['auto', 'auto']}
                    />
                    <Tooltip
                      contentStyle={{ background: 'rgba(0,30,50,0.85)', border: '1px solid rgba(0,200,255,0.3)', fontSize: 12 }}
                      labelStyle={{ color: '#0ff' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {stats && stats.p90 > stats.p10 && (
                      <ReferenceArea y1={stats.p10} y2={stats.p90} strokeOpacity={0} fill="rgba(0,255,255,0.08)" />
                    )}
                    {stats && <ReferenceLine y={stats.p10} stroke="#0ff" strokeDasharray="4 4" ifOverflow="discard" />}
                    {stats && <ReferenceLine y={stats.p90} stroke="#0ff" strokeDasharray="4 4" ifOverflow="discard" />}
                    {seriesEnabled.totalAdded && (
                      <Line type="monotone" dataKey="totalAdded" stroke="#0ff" strokeWidth={2} dot={false} animationDuration={400} />
                    )}
                    {seriesEnabled.totalFailed && (
                      <Line type="monotone" dataKey="totalFailed" stroke="#ff4d6d" strokeWidth={2} dot={false} animationDuration={400} />
                    )}
                    {seriesEnabled.retries && (
                      <Line type="monotone" dataKey="retries" stroke="#ffb347" strokeWidth={2} dot={false} animationDuration={400} />
                    )}
                    {seriesEnabled.decryptFailures && (
                      <Line type="monotone" dataKey="decryptFailures" stroke="#c084fc" strokeWidth={2} dot={false} animationDuration={400} />
                    )}
                    {seriesEnabled.successRate && (
                      <Line type="monotone" dataKey="successRate" stroke="#10b981" strokeWidth={2} dot={<AnomalyDot />} animationDuration={400} />
                    )}
                    <Brush
                      dataKey="time"
                      height={20}
                      travellerWidth={10}
                      stroke="#0ff"
                      fill={theme === 'dark' ? 'rgba(0,40,55,0.6)' : 'rgba(255,255,255,0.8)'}
                      tickFormatter={() => ''}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            <div
              style={{
                marginTop: 6,
                fontSize: 10,
                letterSpacing: 0.5,
                color: theme === 'dark' ? '#8fd' : '#024',
                display: 'flex',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              <span>Samples: {chartData.length}</span>
              <span>
                Window: last{' '}
                {chartData.length * 5 / 60 < 1
                  ? `${Math.max(1, Math.round(chartData.length * 5))}s`
                  : `${(chartData.length * 5 / 60).toFixed(1)}m`}
              </span>
              {smoothWindow > 1 && <span>Smoothing: {smoothWindow} pt</span>}
              {stats && <span>Band: p{percentiles.low} {stats.p10.toFixed(1)}% / p{percentiles.high} {stats.p90.toFixed(1)}%</span>}
              {stats && <span>Anomalies: {stats.anomalyIdx.size}</span>}
              {stats && stats.anomalyIdx.size > 0 && (
                <a
                  href="/api/ingest/anomalies?download=1"
                  style={{ color: '#0ff', textDecoration: 'underline' }}
                  aria-label="Download all anomalies jsonl"
                >
                  Download
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: any; theme: string }> = ({ label, value, theme }) => (
  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 90 }}>
    <span style={{ fontSize: 10, letterSpacing: 1, textTransform: 'uppercase', opacity: 0.55 }}>{label}</span>
    <span
      style={{
        fontSize: 14,
        fontWeight: 500,
        color: theme === 'dark' ? '#cfe' : '#024',
        textShadow: theme === 'dark' ? '0 0 6px rgba(0,200,255,0.5)' : 'none',
      }}
    >
      {value}
    </span>
  </div>
);

export default IngestionMetricsHologram;