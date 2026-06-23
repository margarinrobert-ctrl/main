"use client";

import { ColorType, createChart, type IChartApi, type Time } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { loadHistory } from "@/lib/client-data";
import type { HistoryBar } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function PriceChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [bars, setBars] = useState<HistoryBar[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const { bars, source } = await loadHistory(symbol);
        if (cancelled) return;
        setSource(source);
        setBars(bars);
        setState(bars.length ? "ok" : "empty");
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
    if (state !== "ok" || !containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 300,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#a3a3a3" },
      grid: { vertLines: { color: "#262626" }, horzLines: { color: "#262626" } },
      timeScale: { borderColor: "#404040" },
      rightPriceScale: { borderColor: "#404040" },
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: "#34d399",
      downColor: "#f87171",
      borderVisible: false,
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });
    series.setData(
      bars.map((b) => ({
        time: b.timestamp.slice(0, 10) as Time,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    chart.timeScale().fitContent();

    const onResize = () => chart.applyOptions({ width: containerRef.current?.clientWidth });
    onResize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [state, bars]);

  return (
    <div className="glass p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Price · {symbol}</h2>
        {source && <span className="text-xs text-neutral-500">src: {source}</span>}
      </div>
      {state === "loading" && <Loading />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No price history." />}
      <div ref={containerRef} className={state === "ok" ? "" : "hidden"} />
    </div>
  );
}
