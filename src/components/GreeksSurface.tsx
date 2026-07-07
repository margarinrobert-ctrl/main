"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { fmtUsd, greekSurface, type GreekSurface, type SurfaceMetric } from "@/lib/flow/analytics";
import { loadChain } from "@/lib/client-data";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const METRICS: { key: SurfaceMetric; label: string }[] = [
  { key: "gex", label: "GEX (γ$)" },
  { key: "dex", label: "DEX (Δ$)" },
  { key: "vanna", label: "Vanna" },
  { key: "charm", label: "Charm" },
  { key: "oi", label: "Open int." },
  { key: "volume", label: "Volume" },
  { key: "iv", label: "Implied vol" },
];

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
function mix(c1: string, c2: string, t: number): [number, number, number] {
  const a = hexToRgb(c1);
  const b = hexToRgb(c2);
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
}
// signed: put-red (−) → graphite (0) → call-emerald (+). unsigned: graphite → emerald → cyan.
function colorFor(h: number, signed: boolean): [number, number, number] {
  if (signed) {
    const t = clamp(h, -1, 1);
    return t >= 0 ? mix("#1f2937", "#34d399", t) : mix("#1f2937", "#f87171", -t);
  }
  const t = clamp(h, 0, 1);
  return t < 0.5 ? mix("#141a24", "#10b981", t / 0.5) : mix("#10b981", "#22d3ee", (t - 0.5) / 0.5);
}
function fmtVal(v: number, metric: SurfaceMetric): string {
  if (metric === "oi" || metric === "volume") return Math.round(v).toLocaleString();
  if (metric === "iv") return `${(v * 100).toFixed(1)}%`;
  return fmtUsd(v);
}

interface View {
  az: number;
  tilt: number;
  zoom: number;
}
interface Hover {
  i: number;
  j: number;
  sx: number;
  sy: number;
  strike: number;
  exp: string;
  val: number;
}

// Light direction in screen space (from upper-front-left), normalized.
const LIGHT = (() => {
  const v: [number, number, number] = [-0.45, 0.75, 0.5];
  const m = Math.hypot(...v);
  return [v[0] / m, v[1] / m, v[2] / m] as [number, number, number];
})();

export function GreeksSurface({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [metric, setMetric] = useState<SurfaceMetric>("gex");
  const [spin, setSpin] = useState(false);
  const [wire, setWire] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewRef = useRef<View>({ az: 40, tilt: 0.62, zoom: 1 });
  const drag = useRef<{ x: number; y: number; az: number; tilt: number } | null>(null);
  const rafRef = useRef(0);
  const sizeRef = useRef({ w: 800, h: 460 });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const res = await loadChain(symbol);
        if (cancelled) return;
        setChain(res.chain);
        setSpot(res.spot);
        setState(res.chain.length ? "ok" : "empty");
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Network error");
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const surface = useMemo(() => greekSurface(chain, spot, metric, 29), [chain, spot, metric]);
  const zmax = useMemo(() => {
    let m = 0;
    for (const row of surface.z) for (const v of row) m = Math.max(m, surface.signed ? Math.abs(v) : v);
    return m || 1;
  }, [surface]);
  const spotIdx = useMemo(() => {
    if (spot == null || !surface.strikes.length) return -1;
    let idx = 0;
    let best = Infinity;
    surface.strikes.forEach((s, i) => {
      const d = Math.abs(s - spot);
      if (d < best) {
        best = d;
        idx = i;
      }
    });
    return idx;
  }, [surface.strikes, spot]);
  const peak = useMemo(() => {
    let best: { v: number; strike: number; exp: string } | null = null;
    surface.z.forEach((row, j) =>
      row.forEach((v, i) => {
        if (best == null || Math.abs(v) > Math.abs(best.v)) best = { v, strike: surface.strikes[i], exp: surface.expirations[j]?.label ?? "" };
      }),
    );
    return best as { v: number; strike: number; exp: string } | null;
  }, [surface]);

  const renderable = surface.strikes.length >= 2 && surface.expirations.length >= 2;

  // ── Imperative canvas renderer (no React churn; smooth spin) ─────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap || state !== "ok" || !renderable) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const project = (i: number, j: number, h: number, v: View, geo: { CX: number; CY: number; SX: number; SY: number; Z: number; cosA: number; sinA: number; nx: number; ny: number }) => {
      const u = (i / (geo.nx - 1)) * 2 - 1;
      const w = (j / (geo.ny - 1)) * 2 - 1;
      const rx = u * geo.cosA - w * geo.sinA;
      const ry = u * geo.sinA + w * geo.cosA;
      return { x: geo.CX + rx * geo.SX * v.zoom, y: geo.CY + ry * geo.SY * v.tilt * v.zoom - h * geo.Z * v.zoom, depth: ry };
    };

    const draw = () => {
      const { w: W, h: H } = sizeRef.current;
      const v = viewRef.current;
      const nx = surface.strikes.length;
      const ny = surface.expirations.length;
      const A = (v.az * Math.PI) / 180;
      const geo = { CX: W / 2, CY: H * 0.6, SX: W * 0.34, SY: H * 0.4, Z: H * 0.34, cosA: Math.cos(A), sinA: Math.sin(A), nx, ny };
      const hOf = (val: number) => (surface.signed ? clamp(val / zmax, -1, 1) : clamp(val / zmax, 0, 1));
      const baseH = surface.signed ? 0 : 0; // baseline plane at h=0

      ctx.clearRect(0, 0, W, H);
      const bg = ctx.createRadialGradient(W * 0.5, H * 0.22, 0, W * 0.5, H * 0.55, H * 0.9);
      bg.addColorStop(0, "rgba(16,185,129,0.05)");
      bg.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // floor grid at baseline
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      const gi = Math.max(1, Math.round(nx / 10));
      const gj = 1;
      for (let i = 0; i < nx; i += gi) {
        ctx.beginPath();
        for (let j = 0; j < ny; j++) {
          const p = project(i, j, baseH, v, geo);
          j === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }
      for (let j = 0; j < ny; j += gj) {
        ctx.beginPath();
        for (let i = 0; i < nx; i++) {
          const p = project(i, j, baseH, v, geo);
          i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }

      // quads with normal-based lighting; sort far→near (painter's, exact for a height field)
      const hExag = 1.35;
      type Q = { pts: { x: number; y: number }[]; fill: string; depth: number };
      const quads: Q[] = [];
      for (let j = 0; j < ny - 1; j++) {
        for (let i = 0; i < nx - 1; i++) {
          const z00 = surface.z[j][i];
          const z10 = surface.z[j][i + 1];
          const z11 = surface.z[j + 1][i + 1];
          const z01 = surface.z[j + 1][i];
          const h00 = hOf(z00);
          const h10 = hOf(z10);
          const h11 = hOf(z11);
          const h01 = hOf(z01);
          const p00 = project(i, j, h00, v, geo);
          const p10 = project(i + 1, j, h10, v, geo);
          const p11 = project(i + 1, j + 1, h11, v, geo);
          const p01 = project(i, j + 1, h01, v, geo);
          // world-space normal in (u,v,h·hExag); scale u,v to grid spacing ~2/n
          const du = 2 / (nx - 1);
          const dwv = 2 / (ny - 1);
          const ax = du;
          const ay = 0;
          const az = (h10 - h00) * hExag;
          const bx = 0;
          const by = dwv;
          const bz = (h01 - h00) * hExag;
          let nxn = ay * bz - az * by;
          let nyn = az * bx - ax * bz;
          let nzn = ax * by - ay * bx;
          const nm = Math.hypot(nxn, nyn, nzn) || 1;
          nxn /= nm;
          nyn /= nm;
          nzn /= nm;
          // rotate normal's ground plane by azimuth so the light is fixed in screen space
          const rnx = nxn * geo.cosA - nyn * geo.sinA;
          const rny = nxn * geo.sinA + nyn * geo.cosA;
          const lambert = clamp(0.42 + 0.62 * Math.max(0, rnx * LIGHT[0] + rny * LIGHT[1] + nzn * LIGHT[2]), 0, 1.15);
          const avg = (z00 + z10 + z11 + z01) / 4;
          const [r, g, b] = colorFor(hOf(avg), surface.signed);
          quads.push({
            pts: [p00, p10, p11, p01],
            fill: `rgb(${clamp(Math.round(r * lambert), 0, 255)},${clamp(Math.round(g * lambert), 0, 255)},${clamp(Math.round(b * lambert), 0, 255)})`,
            depth: (p00.depth + p10.depth + p11.depth + p01.depth) / 4,
          });
        }
      }
      quads.sort((a, b) => b.depth - a.depth);
      ctx.lineJoin = "round";
      for (const q of quads) {
        ctx.beginPath();
        ctx.moveTo(q.pts[0].x, q.pts[0].y);
        for (let k = 1; k < 4; k++) ctx.lineTo(q.pts[k].x, q.pts[k].y);
        ctx.closePath();
        if (wire) {
          ctx.strokeStyle = q.fill;
          ctx.lineWidth = 1;
          ctx.stroke();
        } else {
          ctx.fillStyle = q.fill;
          ctx.fill();
          ctx.strokeStyle = "rgba(255,255,255,0.06)";
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }

      // ridges on top: spot column (dashed white) + selected-expiration row (emerald glow)
      const expIdx = exp === "ALL" ? -1 : surface.expirations.findIndex((e) => e.label === exp);
      if (expIdx >= 0) {
        ctx.save();
        ctx.strokeStyle = "#34d399";
        ctx.lineWidth = 2.4;
        ctx.shadowColor = "rgba(52,211,153,0.8)";
        ctx.shadowBlur = 8;
        ctx.beginPath();
        for (let i = 0; i < nx; i++) {
          const p = project(i, expIdx, hOf(surface.z[expIdx][i]), v, geo);
          i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
        ctx.restore();
      }
      if (spotIdx >= 0) {
        ctx.save();
        ctx.strokeStyle = "#fafafa";
        ctx.lineWidth = 1.6;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        for (let j = 0; j < ny; j++) {
          const p = project(spotIdx, j, hOf(surface.z[j][spotIdx]), v, geo);
          j === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
        ctx.restore();
      }

      // axis labels (strikes along the front edge, expiries along the near side)
      ctx.fillStyle = "#8b93a1";
      ctx.font = "10px ui-monospace, monospace";
      ctx.textAlign = "center";
      const everyK = Math.max(1, Math.round(nx / 7));
      for (let i = 0; i < nx; i += everyK) {
        const p = project(i, 0, baseH, v, geo);
        ctx.fillText(String(surface.strikes[i]), p.x, p.y + 13);
      }
      ctx.textAlign = "right";
      for (let j = 0; j < ny; j++) {
        const e = surface.expirations[j];
        const p = project(0, j, baseH, v, geo);
        ctx.fillText(e.dte != null ? `${e.dte}d` : e.label.slice(5), p.x - 8, p.y + 3);
      }

      // hover marker
      const hv = hoverStateRef.current;
      if (hv) {
        const p = project(hv.i, hv.j, hOf(surface.z[hv.j][hv.i]), v, geo);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = "#fafafa";
        ctx.shadowColor = "rgba(52,211,153,0.9)";
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    };

    const requestDraw = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(draw);
    };
    drawRef.current = requestDraw;

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const W = Math.max(320, rect.width);
      const H = clamp(rect.width * 0.56, 320, 520);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      sizeRef.current = { w: W, h: H };
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      requestDraw();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(rafRef.current);
      drawRef.current = null;
    };
  }, [surface, zmax, spotIdx, exp, wire, state, renderable]);

  const drawRef = useRef<null | (() => void)>(null);
  const hoverStateRef = useRef<Hover | null>(null);
  hoverStateRef.current = hover;

  // spin loop — mutate azimuth in the ref and redraw imperatively
  useEffect(() => {
    if (!spin || state !== "ok" || !renderable) return;
    let raf = 0;
    let last = performance.now();
    const loop = (t: number) => {
      const dt = t - last;
      last = t;
      viewRef.current.az = (viewRef.current.az + dt * 0.018) % 360;
      drawRef.current?.();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [spin, state, renderable]);

  // ── pointer interaction ──────────────────────────────────────────────────
  const onDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, az: viewRef.current.az, tilt: viewRef.current.tilt };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (drag.current) {
      const dx = e.clientX - drag.current.x;
      const dy = e.clientY - drag.current.y;
      viewRef.current.az = (drag.current.az + dx * 0.4) % 360;
      viewRef.current.tilt = clamp(drag.current.tilt - dy * 0.0025, 0.16, 0.95);
      if (hover) setHover(null);
      drawRef.current?.();
      return;
    }
    // hover hit-test: nearest projected vertex
    if (!canvas || spin || !renderable) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const { w: W, h: H } = sizeRef.current;
    const v = viewRef.current;
    const nx = surface.strikes.length;
    const ny = surface.expirations.length;
    const A = (v.az * Math.PI) / 180;
    const cosA = Math.cos(A);
    const sinA = Math.sin(A);
    const CX = W / 2;
    const CY = H * 0.6;
    const SX = W * 0.34;
    const SY = H * 0.4;
    const Z = H * 0.34;
    const hOf = (val: number) => (surface.signed ? clamp(val / zmax, -1, 1) : clamp(val / zmax, 0, 1));
    let best: Hover | null = null;
    let bestD = 22 * 22;
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const u = (i / (nx - 1)) * 2 - 1;
        const w = (j / (ny - 1)) * 2 - 1;
        const rx = u * cosA - w * sinA;
        const ry = u * sinA + w * cosA;
        const sx = CX + rx * SX * v.zoom;
        const sy = CY + ry * SY * v.tilt * v.zoom - hOf(surface.z[j][i]) * Z * v.zoom;
        const d = (sx - mx) ** 2 + (sy - my) ** 2;
        if (d < bestD) {
          bestD = d;
          best = { i, j, sx, sy, strike: surface.strikes[i], exp: surface.expirations[j].label, val: surface.z[j][i] };
        }
      }
    }
    if ((best?.i !== hover?.i || best?.j !== hover?.j)) {
      setHover(best);
      drawRef.current?.();
    }
  };
  const onUp = () => {
    drag.current = null;
  };
  const onLeave = () => {
    drag.current = null;
    if (hover) {
      setHover(null);
      drawRef.current?.();
    }
  };
  const onWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    viewRef.current.zoom = clamp(viewRef.current.zoom * (e.deltaY < 0 ? 1.08 : 0.93), 0.6, 2.2);
    drawRef.current?.();
  };
  const resetView = () => {
    viewRef.current = { az: 40, tilt: 0.62, zoom: 1 };
    setSpin(false);
    drawRef.current?.();
  };

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="lbl mb-1">3D greeks surface</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMetric(m.key)}
              aria-pressed={metric === m.key}
              className={`rounded-lg px-2.5 py-2 text-xs font-medium transition ${metric === m.key ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
            >
              {m.label}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-white/10" />
          <button onClick={() => setWire((w) => !w)} aria-pressed={wire} className={`rounded-lg px-2.5 py-2 text-xs font-medium transition ${wire ? "bg-white/10 text-neutral-100" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}>
            Wire
          </button>
          <button onClick={() => setSpin((s) => !s)} aria-pressed={spin} className={`flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium transition ${spin ? "bg-white/10 text-neutral-100" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}>
            <svg aria-hidden viewBox="0 0 12 12" className="h-2.5 w-2.5">{spin ? <path fill="currentColor" d="M2 2h3v8H2zM7 2h3v8H7z" /> : <path fill="currentColor" d="M3 2l7 4-7 4z" />}</svg>
            Spin
          </button>
          <button onClick={resetView} className="rounded-lg px-2.5 py-2 text-xs font-medium text-neutral-400 transition hover:bg-white/5 hover:text-neutral-200">
            Reset
          </button>
        </div>
      </div>

      {state === "loading" && <Loading label="Loading greeks surface…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="Greeks unavailable for this chain." />}
      {state === "ok" && !renderable && <EmptyState label="Need ≥2 expirations and ≥2 strikes to render a surface." />}
      {state === "ok" && renderable && (
        <>
          <p className="mb-2 text-xs text-neutral-500">
            x = strike · y = expiration (near→far) · z = {METRICS.find((m) => m.key === metric)?.label}. Drag to rotate/tilt · scroll to zoom · hover a node.
          </p>
          <div ref={wrapRef} className="relative w-full select-none overflow-hidden rounded-xl border border-white/[0.06] bg-[#07080c]">
            <canvas
              ref={canvasRef}
              className="w-full cursor-grab touch-none active:cursor-grabbing"
              onPointerDown={onDown}
              onPointerMove={onMove}
              onPointerUp={onUp}
              onPointerLeave={onLeave}
              onWheel={onWheel}
            />
            {hover && (
              <div
                className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+10px)] rounded-lg border border-white/12 bg-[#0a0b10]/95 px-2.5 py-1.5 text-[11px] shadow-panel backdrop-blur"
                style={{ left: hover.sx, top: hover.sy }}
              >
                <div className="font-mono text-neutral-300">
                  {hover.strike} · {hover.exp.slice(5)}
                </div>
                <div className={`font-mono font-semibold ${surface.signed ? (hover.val >= 0 ? "text-call" : "text-put") : "text-accent-bright"}`}>{fmtVal(hover.val, metric)}</div>
              </div>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.05] pt-3 text-[11px] text-neutral-500">
            <div className="flex items-center gap-2">
              <span>{surface.signed ? "−" : "low"}</span>
              <span className="inline-block h-2 w-32 rounded" style={{ background: surface.signed ? "linear-gradient(90deg,#f87171,#1f2937,#34d399)" : "linear-gradient(90deg,#141a24,#10b981,#22d3ee)" }} />
              <span>{surface.signed ? "+" : "high"}</span>
            </div>
            {peak && (
              <span>
                Peak {METRICS.find((m) => m.key === metric)?.label}: <span className="text-neutral-200">{fmtVal(peak.v, metric)}</span> @ {peak.strike} ({peak.exp.slice(5)})
              </span>
            )}
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-4 border-t-2 border-dashed border-white/70" /> spot ridge
            </span>
          </div>
        </>
      )}
    </div>
  );
}
