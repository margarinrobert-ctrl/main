"use client";

import { ColorType, createChart, type IChartApi, type IPriceLine, type ISeriesApi, LineStyle, type Time } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import type { DarkPoolDay, DarkPoolProfile } from "@/lib/flow/darkpool";

const fmtP = (p: number) => (Math.abs(p) >= 1000 ? String(Math.round(p)) : String(Math.round(p * 100) / 100));

/** Daily candles over the off-exchange window with the dark-pool volume-by-price levels drawn as price lines. */
export function DarkPoolLevelsChart({ days, levels }: { days: DarkPoolDay[]; levels: DarkPoolProfile }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);

  const candles = useMemo(
    () =>
      days
        .filter((d) => d.open != null && d.high != null && d.low != null && d.close != null)
        .map((d) => ({ time: d.date as Time, open: d.open as number, high: d.high as number, low: d.low as number, close: d.close as number }))
        .sort((a, b) => String(a.time).localeCompare(String(b.time))),
    [days],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 360,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#a3a3a3" },
      grid: { vertLines: { color: "#1f1f1f" }, horzLines: { color: "#1f1f1f" } },
      timeScale: { borderColor: "#404040" },
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
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !candles.length) return;
    seriesRef.current.setData(candles);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const pl of linesRef.current) series.removePriceLine(pl);
    const lines: IPriceLine[] = [];
    for (const l of levels.levels) {
      const isPoc = levels.poc != null && Math.abs(l.price - levels.poc) < 1e-9;
      lines.push(
        series.createPriceLine({
          price: l.price,
          color: isPoc ? "#c084fc" : "#8b5cf6",
          lineWidth: isPoc ? 3 : 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: isPoc ? `DP POC ${fmtP(l.price)}` : `DP ${fmtP(l.price)}`,
        }),
      );
    }
    if (levels.vah != null) lines.push(series.createPriceLine({ price: levels.vah, color: "#6b7280", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "VAH" }));
    if (levels.val != null) lines.push(series.createPriceLine({ price: levels.val, color: "#6b7280", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "VAL" }));
    linesRef.current = lines;
  }, [levels, candles]);

  if (!candles.length) return <p className="text-[11px] text-neutral-500">No price history to plot dark-pool levels against.</p>;
  return <div ref={containerRef} />;
}
