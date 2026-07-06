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
import { CHART, LW_THEME } from "@/lib/chartTheme";
import { resampleBars } from "@/lib/resample";
import { EmptyState, Loading, SectionHeader, Stat } from "./states";

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
    mk(callResistance(by, spot), "#f87171", "Call Res", S),
    mk(putSupport(by, spot), "#34d399", "Put Sup", S),
    mk(gammaFlipNearest(by, spot), "#a78bfa", "HVL", S),
    mk(magnet, "#fbbf24", "Magnet", D),
    mk(front ? maxPain(chain, front) : null, "#fbbf24", "Max Pain", D),
    mk(callOiWall(oi), "rgba(248,113,113,0.55)", "Call OI", Dot),
    mk(putOiWall(oi), "rgba(52,211,153,0.55)", "Put OI", Dot),
    mk(em != null ? spot + em : null, "#fbbf24", "+1σ EM", Dot),
    mk(em != null ? spot - em : null, "#fbbf24", "−1σ EM", Dot),
    ...ladder.map((x, i) => mk(x.strike, "rgba(255,255,255,0.35)", `GEX ${i + 1}`, Dot)),
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
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: LW_THEME.layout.textColor, fontSize: LW_THEME.layout.fontSize },
      grid: { vertLines: { color: LW_THEME.grid.vertLines.color }, horzLines: { color: LW_THEME.grid.horzLines.color } },
      timeScale: { borderColor: LW_THEME.timeScale.borderColor, timeVisible: tf.id !== "1d", secondsVisible: false },
      rightPriceScale: { borderColor: LW_THEME.rightPriceScale.borderColor },
      crosshair: { mode: 0 },
      handleScroll: { vertTouchDrag: false },
    });
    chartRef.current = chart;
    seriesRef.current = chart.addCandlestickSeries({ upColor: CHART.call, downColor: CHART.put, borderVisible: false, wickUpColor: CHART.call, wickDownColor: CHART.put });
    const onResize = () => chart.applyOptions({ width: containerRef.current?.clientWidth });
    onResize();
    const ro = new ResizeObserver(onResize);
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
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
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="lbl mb-1">Levels chart</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
        </div>
        <div className="tabs-scroll max-w-full">
          {TIMEFRAMES.map((t) => (
            <button
              key={t.id}
              onClick={() => setTf(t)}
              aria-pressed={tf.id === t.id}
              className={`tab-pill rounded-lg px-3 py-2 text-xs font-medium transition ${tf.id === t.id ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2.5 sm:grid-cols-5">
        <Stat label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
        <Stat
          label="Dealer γ"
          value={greeks.ngex == null ? "—" : greeks.ngex >= 0 ? "Long γ" : "Short γ"}
          sub={greeks.ngex == null ? "" : `${fmtUsd(greeks.ngex)}/1%`}
          tone={greeks.ngex == null ? undefined : greeks.ngex >= 0 ? "call" : "put"}
        />
        <Stat label="Net Δ exp" value={greeks.ndex == null ? "—" : fmtUsd(greeks.ndex)} />
        <Stat label="Vanna" value={greeks.vanna == null ? "—" : fmtUsd(greeks.vanna)} sub="per 1% IV" />
        <Stat label="Charm" value={greeks.charm == null ? "—" : `${fmtUsd(greeks.charm)}/d`} sub="Δ decay" />
      </div>

      {loading && bars.length === 0 ? (
        <Loading label="Loading candles…" />
      ) : bars.length === 0 ? (
        <EmptyState label="No intraday candles returned." hint="Try another timeframe — shorter ranges depend on session hours." />
      ) : (
        <div ref={containerRef} />
      )}

      <div className="mt-3 space-y-1.5 border-t border-white/[0.05] pt-3">
        {[
          { name: "Walls", match: (t: string) => /Res|Sup|OI/.test(t) },
          { name: "Model", match: (t: string) => /HVL|Magnet|Max Pain|EM/.test(t) },
          { name: "GEX ladder", match: (t: string) => /^GEX /.test(t) },
        ].map((g) => {
          const items = levels.filter((l) => g.match(l.title));
          if (!items.length) return null;
          return (
            <div key={g.name} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="lbl w-20 shrink-0">{g.name}</span>
              {items.map((l) => (
                <span key={l.title} className="inline-flex items-center gap-1 text-[10px] text-neutral-500">
                  <span className="inline-block h-2 w-2 rounded-sm" style={{ background: l.color }} />
                  {l.title} <span className="font-mono tabular-nums text-neutral-400">{Math.round(l.price * 100) / 100}</span>
                </span>
              ))}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-neutral-600">Levels redraw as the chain updates. Educational — not advice.</p>
    </div>
  );
}
