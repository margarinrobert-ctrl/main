"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { fmtUsd, greekSurface, type SurfaceMetric } from "@/lib/flow/analytics";
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

// viewBox geometry
const VBW = 820;
const VBH = 540;
const CX = 410;
const CY = 340;
const SPAN_X = 300;
const SPAN_Y = 250;
const Z_SPAN = 150;

function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function lerp(a: number, b: number, t: number) {
  return Math.round(a + (b - a) * t);
}
function mix(c1: string, c2: string, t: number): string {
  const a = hexToRgb(c1);
  const b = hexToRgb(c2);
  return `rgb(${lerp(a[0], b[0], t)},${lerp(a[1], b[1], t)},${lerp(a[2], b[2], t)})`;
}
// signed: put-red (−) → graphite (0) → call-emerald (+).  unsigned: graphite → emerald → cyan.
function colorFor(h: number, signed: boolean): string {
  if (signed) {
    const t = Math.max(-1, Math.min(1, h));
    return t >= 0 ? mix("#1f2937", "#34d399", t) : mix("#1f2937", "#f87171", -t);
  }
  const t = Math.max(0, Math.min(1, h));
  return t < 0.5 ? mix("#151a24", "#10b981", t / 0.5) : mix("#10b981", "#22d3ee", (t - 0.5) / 0.5);
}

function fmtVal(v: number, metric: SurfaceMetric): string {
  if (metric === "oi" || metric === "volume") return Math.round(v).toLocaleString();
  if (metric === "iv") return `${(v * 100).toFixed(1)}%`;
  return fmtUsd(v);
}

/** Scale an "rgb(r,g,b)" string by a brightness factor (for pseudo-lighting on the surface). */
function shade(rgb: string, f: number): string {
  const m = /rgb\((\d+),(\d+),(\d+)\)/.exec(rgb);
  if (!m) return rgb;
  const s = (x: number) => Math.max(0, Math.min(255, Math.round(x * f)));
  return `rgb(${s(+m[1])},${s(+m[2])},${s(+m[3])})`;
}

export function GreeksSurface({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [metric, setMetric] = useState<SurfaceMetric>("gex");
  const [azimuth, setAzimuth] = useState(38);
  const [tilt, setTilt] = useState(0.52);
  const [spin, setSpin] = useState(false);
  const drag = useRef<{ x: number; y: number; az: number; tilt: number } | null>(null);

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

  useEffect(() => {
    if (!spin) return;
    let raf = 0;
    let last = performance.now();
    const loop = (t: number) => {
      const dt = t - last;
      last = t;
      setAzimuth((a) => (a + dt * 0.02) % 360);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [spin]);

  const surface = useMemo(() => greekSurface(chain, spot, metric), [chain, spot, metric]);

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

  const render = useMemo(() => {
    const nx = surface.strikes.length;
    const ny = surface.expirations.length;
    if (nx < 2 || ny < 2) return null;
    const A = (azimuth * Math.PI) / 180;
    const cosA = Math.cos(A);
    const sinA = Math.sin(A);
    const hOf = (v: number) => (surface.signed ? Math.max(-1, Math.min(1, v / zmax)) : Math.max(0, Math.min(1, v / zmax)));
    const project = (ix: number, iy: number, h: number) => {
      const u = (ix / (nx - 1)) * 2 - 1;
      const v = (iy / (ny - 1)) * 2 - 1;
      const rx = u * cosA - v * sinA;
      const ry = u * sinA + v * cosA;
      return { x: CX + rx * SPAN_X, y: CY + ry * SPAN_Y * tilt - h * Z_SPAN, depth: ry };
    };

    // surface quads
    const quads: { path: string; fill: string; depth: number }[] = [];
    for (let j = 0; j < ny - 1; j++) {
      for (let i = 0; i < nx - 1; i++) {
        const c00 = surface.z[j][i];
        const c10 = surface.z[j][i + 1];
        const c11 = surface.z[j + 1][i + 1];
        const c01 = surface.z[j + 1][i];
        const p00 = project(i, j, hOf(c00));
        const p10 = project(i + 1, j, hOf(c10));
        const p11 = project(i + 1, j + 1, hOf(c11));
        const p01 = project(i, j + 1, hOf(c01));
        const avg = (c00 + c10 + c11 + c01) / 4;
        const depthAvg = (p00.depth + p10.depth + p11.depth + p01.depth) / 4;
        const hA = hOf(avg);
        // pseudo-lighting: taller cells brighter, far (deeper) cells dimmer
        const lightF = Math.max(0.6, Math.min(1.2, (0.84 + 0.3 * Math.abs(hA)) * (1 - 0.13 * ((depthAvg + 1.4) / 2.8))));
        quads.push({
          path: `M${p00.x},${p00.y} L${p10.x},${p10.y} L${p11.x},${p11.y} L${p01.x},${p01.y} Z`,
          fill: shade(colorFor(hA, surface.signed), lightF),
          depth: depthAvg,
        });
      }
    }
    quads.sort((a, b) => a.depth - b.depth); // back (far) first

    // base-plane outline (h = 0)
    const b0 = project(0, 0, 0);
    const b1 = project(nx - 1, 0, 0);
    const b2 = project(nx - 1, ny - 1, 0);
    const b3 = project(0, ny - 1, 0);
    const basePath = `M${b0.x},${b0.y} L${b1.x},${b1.y} L${b2.x},${b2.y} L${b3.x},${b3.y} Z`;

    // spot ridge (column nearest spot, front→back along expirations)
    let ridge: string | null = null;
    if (spotIdx >= 0) {
      const pts: string[] = [];
      for (let j = 0; j < ny; j++) {
        const p = project(spotIdx, j, hOf(surface.z[j][spotIdx]));
        pts.push(`${p.x},${p.y}`);
      }
      ridge = `M${pts.join(" L")}`;
    }

    // selected-expiration ridge (a row across strikes) — highlight, since exp is an axis here
    let expRidge: string | null = null;
    const expIdx = exp === "ALL" ? -1 : surface.expirations.findIndex((e) => e.label === exp);
    if (expIdx >= 0) {
      const pts: string[] = [];
      for (let i = 0; i < nx; i++) {
        const p = project(i, expIdx, hOf(surface.z[expIdx][i]));
        pts.push(`${p.x},${p.y}`);
      }
      expRidge = `M${pts.join(" L")}`;
    }

    // strike labels along the j=0 edge; expiration labels along i=0 edge
    const everyK = Math.max(1, Math.round(nx / 8));
    const strikeLabels = surface.strikes
      .map((s, i) => ({ s, i }))
      .filter(({ i }) => i % everyK === 0 || i === nx - 1)
      .map(({ s, i }) => ({ ...project(i, 0, 0), s }));
    const expLabels = surface.expirations.map((e, j) => ({ ...project(0, j, 0), e }));

    return { quads, basePath, ridge, expRidge, strikeLabels, expLabels };
  }, [surface, azimuth, tilt, zmax, spotIdx, exp]);

  const peak = useMemo(() => {
    let best: { v: number; strike: number; exp: string } | null = null;
    surface.z.forEach((row, j) =>
      row.forEach((v, i) => {
        if (best == null || Math.abs(v) > Math.abs(best.v)) best = { v, strike: surface.strikes[i], exp: surface.expirations[j]?.label ?? "" };
      }),
    );
    return best as { v: number; strike: number; exp: string } | null;
  }, [surface]);

  const onDown = (e: React.PointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, az: azimuth, tilt };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    setAzimuth((drag.current.az + dx * 0.4) % 360);
    setTilt(Math.max(0.15, Math.min(0.9, drag.current.tilt - dy * 0.0025)));
  };
  const onUp = () => {
    drag.current = null;
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
              className={`rounded-lg px-2.5 py-2 text-xs font-medium transition ${
                metric === m.key ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
              }`}
            >
              {m.label}
            </button>
          ))}
          <button
            onClick={() => setSpin((s) => !s)}
            aria-pressed={spin}
            className={`ml-1 flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium transition ${spin ? "bg-white/10 text-neutral-100" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
          >
            <svg aria-hidden viewBox="0 0 12 12" className="h-2.5 w-2.5">
              {spin ? (
                <path fill="currentColor" d="M2 2h3v8H2zM7 2h3v8H7z" />
              ) : (
                <path fill="currentColor" d="M3 2l7 4-7 4z" />
              )}
            </svg>
            Spin
          </button>
        </div>
      </div>

      {state === "loading" && <Loading label="Loading greeks surface…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="Greeks unavailable for this chain." />}
      {state === "ok" && render == null && (
        <EmptyState label="Need ≥2 expirations and ≥2 strikes to render a surface." />
      )}
      {state === "ok" && render != null && (
        <>
          <p className="mb-1 text-xs text-neutral-500">
            x = strike · y = expiration (near→far) · z = {METRICS.find((m) => m.key === metric)?.label}. Drag to rotate / tilt.
          </p>
          <div className="w-full select-none overflow-hidden rounded-lg border border-white/5 bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.06),transparent_60%)]">
            <svg
              viewBox={`0 0 ${VBW} ${VBH}`}
              className="w-full cursor-grab touch-none active:cursor-grabbing"
              onPointerDown={onDown}
              onPointerMove={onMove}
              onPointerUp={onUp}
              onPointerLeave={onUp}
            >
              <defs>
                <filter id="ridgeGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="b" />
                  <feMerge>
                    <feMergeNode in="b" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <path d={render.basePath} fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
              {render.quads.map((q, i) => (
                <path key={i} d={q.path} fill={q.fill} stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} />
              ))}
              {render.expRidge && <path d={render.expRidge} fill="none" stroke="#34d399" strokeWidth={2.6} filter="url(#ridgeGlow)" />}
              {render.ridge && <path d={render.ridge} fill="none" stroke="#f5f5f5" strokeWidth={1.6} strokeDasharray="3 3" />}
              {render.strikeLabels.map((l) => (
                <text key={`s${l.s}`} x={l.x} y={l.y + 14} fontSize={9} fill="#9ca3af" textAnchor="middle">
                  {l.s}
                </text>
              ))}
              {render.expLabels.map((l) => (
                <text key={`e${l.e.label}`} x={l.x - 8} y={l.y} fontSize={9} fill="#9ca3af" textAnchor="end">
                  {l.e.dte != null ? `${l.e.dte}d` : l.e.label.slice(5)}
                </text>
              ))}
            </svg>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.05] pt-3 text-[11px] text-neutral-500">
            <div className="flex items-center gap-2">
              <span>{surface.signed ? "−" : "low"}</span>
              <span
                className="inline-block h-2 w-32 rounded"
                style={{
                  background: surface.signed
                    ? "linear-gradient(90deg,#f87171,#1f2937,#34d399)"
                    : "linear-gradient(90deg,#151a24,#10b981,#22d3ee)",
                }}
              />
              <span>{surface.signed ? "+" : "high"}</span>
            </div>
            {peak && (
              <span>
                Peak {METRICS.find((m) => m.key === metric)?.label}: <span className="text-neutral-200">{fmtVal(peak.v, metric)}</span> @ {peak.strike}{" "}
                ({peak.exp})
              </span>
            )}
            <span className="text-neutral-200">— spot ridge</span>
          </div>
        </>
      )}
    </div>
  );
}
