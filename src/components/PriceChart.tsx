"use client";

import { createChart, type IChartApi, type Time } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { loadHistory } from "@/lib/client-data";
import type { HistoryBar } from "@/lib/barchart/types";
import { CHART, LW_THEME } from "@/lib/chartTheme";
import { Chip, EmptyState, ErrorState, Loading, SectionHeader } from "./states";

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
    const el = containerRef.current;
    const chart = createChart(el, {
      height: 300,
      ...LW_THEME,
      handleScroll: { vertTouchDrag: false },
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: CHART.call,
      downColor: CHART.put,
      borderVisible: false,
      wickUpColor: CHART.call,
      wickDownColor: CHART.put,
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

    chart.applyOptions({ width: el.clientWidth });
    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [state, bars]);

  return (
    <div className="glass fade-up p-4">
      <SectionHeader
        eyebrow="Price history"
        title={symbol}
        right={
          <div className="flex items-center gap-1.5">
            <Chip>Daily</Chip>
            <Chip>Candles</Chip>
          </div>
        }
      />
      <div className="min-h-[300px]">
        {state === "loading" && <Loading label="Loading price history…" />}
        {state === "error" && <ErrorState message={error} />}
        {state === "empty" && <EmptyState label="No price history." />}
        <div ref={containerRef} className={state === "ok" ? "" : "hidden"} />
      </div>
    </div>
  );
}
