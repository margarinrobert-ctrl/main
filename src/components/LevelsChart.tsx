"use client";

import { ColorType, createChart, type IChartApi, type ISeriesApi, type IPriceLine, LineStyle, type Time } from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { loadCandles, loadChain } from "@/lib/client-data";
import {
  atmIv,
  callOiWall,
  callResistance,
  expectedMove1D,
  fmtUsd,
  gammaFlipNearest,
  gexByStrike,
  maxPain,
  netDex,
  netGex,
  oiByStrike,
  putOiWall,
  putSupport,
  secondOrderExposure,
} from "@/lib/flow/analytics";
import { resampleBars } from "@/lib/resample";
import { Loading } from "./states";

const TIMEFRAMES = [
  { id: "1m", label: "1m", interval: "1m", range: "1d", resample: 1 },
  { id: "2m", label: "2m", interval: "2m", range: "5d", resample: 1 },
  { id: "3m", label: "3m", interval: "1m", range: "1d", resample: 3 },
  { id: "5m", label: "5m", interval: "5m", range: "5d", resample: 1 },
  { id: "15m", label: "15m", interval: "15m", range: "1mo", resample: 1 },
  { id: "30m", label: "30m", interval: "30m", range: "1mo", resample: 1 },
  { id: "1h", label: "1h", interval: "60m", range: "3mo", resample: 1 },
  { id: "1d", label: "1D", interval: "1d", range: "6mo", resample: 1 },
] as const;
type TF = (typeof TIMEFRAMES)[number];

interface Level {
  price: number;
  color: string;
  title: string;
  style: LineStyle;
}

function buildLevels(chain: OptionContract[], spot: number | null): Level[] {
  const by = gexByStrike(chain, spot);
  if (!by.length || spot == null) return [];
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const front = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const iv0 = front ? atmIv(chain, spot, front) : null;
  const em = expectedMove1D(spot, iv0)?.abs ?? null;
  const oi = oiByStrike(chain);
  const magnet = by.reduce((m, x) => (Math.abs(x.gex) > Math.abs(m.gex) ? x : m)).strike;
  const ladder = by.filter((x) => x.gex !== 0).sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex)).slice(0, 5);
  const S = LineStyle.Solid;
  const D = LineStyle.Dashed;
  const Dot = LineStyle.Dotted;
  const raw: (Level | null)[] = [
    mk(callResistance(by, spot), "#ef4444", "Call Res", S),
    mk(putSupport(by, spot), "#22c55e", "Put Sup", S),
    mk(gammaFlipNearest(by, spot), "#3b82f6", "HVL", S),
    mk(magnet, "#eab308", "Magnet", D),
    mk(front ? maxPain(chain, front) : null, "#f59e0b", "Max Pain", D),
    mk(callOiWall(oi), "#84cc16", "Call OI", Dot),
    mk(putOiWall(oi), "#a855f7", "Put OI", Dot),
    mk(em != null ? spot + em : null, "#fb923c", "1D Max", Dot),
    mk(em != null ? spot - em : null, "#fb923c", "1D Min", Dot),
    ...ladder.map((x, i) => mk(x.strike, "#2dd4bf", `GEX ${i + 1}`, S)),
  ];
  const tol = Math.max(0.01, spot * 0.0006);
  const out: Level[] = [];
  for (const l of raw) if (l && !out.some((u) => Math.abs(u.price - l.price) <= tol)) out.push(l);
  return out;
}
const mk = (price: number | null, color: string, title: string, style: LineStyle): Level | null =>
  price != null && Number.isFinite(price) ? { price, color, title, style } : null;

export function LevelsChart({ symbol }: { symbol: string }) {
  const [tf, setTf] = useState<TF>(TIMEFRAMES[2]); // default 3m
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<{ time: Time; open: number; high: number; low: number; close: number }[]>([]);
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(true);

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);

  // fetch candles + chain (live), refresh on an interval
  useEffect(() => {
    let cancelled = false;
    const toTime = (ts: string): Time => (tf.id === "1d" ? (ts.slice(0, 10) as Time) : (Math.floor(Date.parse(ts) / 1000) as Time));
    const load = async () => {
      try {
        const [cd, ch] = await Promise.all([
          loadCandles(symbol, tf.interval, tf.range),
          loadChain(symbol).catch(() => ({ chain: [], spot: null, source: "" })),
        ]);
        if (cancelled) return;
        const rb = resampleBars(cd.bars, tf.resample);
        setBars(rb.map((b) => ({ time: toTime(b.timestamp), open: b.open, high: b.high, low: b.low, close: b.close })));
        setChain(("chain" in ch ? ch.chain : []) as OptionContract[]);
        setSpot(("spot" in ch ? ch.spot : null) as number | null);
        setSource(cd.source);
      } catch {
        /* keep last */
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    setLoading(true);
    load();
    const ms = Math.max(20_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 30_000) || 30_000);
    const id = setInterval(load, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol, tf]);

  const levels = useMemo(() => buildLevels(chain, spot), [chain, spot]);
  const greeks = useMemo(() => {
    const so = secondOrderExposure(chain, spot);
    return { ngex: netGex(chain, spot), ndex: netDex(chain, spot), vanna: so.vanna, charm: so.charm };
  }, [chain, spot]);

  // create the chart once per symbol/timeframe
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 380,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#a3a3a3" },
      grid: { vertLines: { color: "#1f1f1f" }, horzLines: { color: "#1f1f1f" } },
      timeScale: { borderColor: "#404040", timeVisible: tf.id !== "1d", secondsVisible: false },
      rightPriceScale: { borderColor: "#404040" },
      crosshair: { mode: 0 },
    });
    chartRef.current = chart;
    seriesRef.current = chart.addCandlestickSeries({ upColor: "#34d399", downColor: "#f87171", borderVisible: false, wickUpColor: "#34d399", wickDownColor: "#f87171" });
    const onResize = () => chart.applyOptions({ width: containerRef.current?.clientWidth });
    onResize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      linesRef.current = [];
    };
  }, [symbol, tf]);

  // push candles
  useEffect(() => {
    if (!seriesRef.current || !bars.length) return;
    seriesRef.current.setData(bars);
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  // (re)draw the GEX level price-lines without rebuilding the chart
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const pl of linesRef.current) series.removePriceLine(pl);
    linesRef.current = levels.map((l) =>
      series.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: l.style, axisLabelVisible: true, title: l.title }),
    );
  }, [levels, bars]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Levels Chart · {symbol}</h2>
        <div className="flex items-center gap-1 text-xs">
          {TIMEFRAMES.map((t) => (
            <button
              key={t.id}
              onClick={() => setTf(t)}
              className={`rounded-md px-2 py-1 transition ${tf.id === t.id ? "bg-emerald-500/15 text-emerald-300" : "text-neutral-400 hover:bg-white/5"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <Stat label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
        <Stat label="Dealer γ" value={greeks.ngex == null ? "—" : greeks.ngex >= 0 ? "Long γ" : "Short γ"} sub={greeks.ngex == null ? "" : `${fmtUsd(greeks.ngex)}/1%`} tone={greeks.ngex == null ? undefined : greeks.ngex >= 0 ? "text-emerald-300" : "text-red-300"} />
        <Stat label="Net Δ exp" value={greeks.ndex == null ? "—" : fmtUsd(greeks.ndex)} />
        <Stat label="Vanna / Charm" value={`${greeks.vanna == null ? "—" : fmtUsd(greeks.vanna)} · ${greeks.charm == null ? "—" : fmtUsd(greeks.charm) + "/d"}`} />
      </div>

      {loading && bars.length === 0 ? <Loading label="Loading candles…" /> : <div ref={containerRef} />}

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-neutral-500">
        {levels.map((l) => (
          <span key={l.title} className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: l.color }} />
            {l.title} {Math.round(l.price * 100) / 100}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-neutral-500">
        Levels redraw as the chain updates. Educational — not advice.
      </p>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-base ${tone ?? "text-neutral-100"}`}>{value}</div>
      {sub ? <div className="text-[10px] text-neutral-500">{sub}</div> : null}
    </div>
  );
}
