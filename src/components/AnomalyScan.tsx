"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { detectAnomalies, type AnomState, type Severity } from "@/lib/flow/anomaly";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sevChip: Record<Severity, string> = {
  extreme: "border-red-500/40 bg-red-500/10 text-red-300",
  elevated: "border-amber-500/40 bg-amber-500/10 text-amber-300",
};
const dirColor = (d: string) => (d === "up" ? "text-emerald-300" : d === "down" ? "text-red-300" : "text-neutral-300");
const dirArrow = (d: string) => (d === "up" ? "▲" : d === "down" ? "▼" : "•");
const stateChip: Record<AnomState, string> = {
  anomalous: "border-red-500/40 bg-red-500/10 text-red-300",
  watch: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  calm: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
};

function ScoreMeter({ score }: { score: number }) {
  return (
    <div className="min-w-[200px] flex-1">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-neutral-500">Anomaly score</span>
        <span className="font-mono text-neutral-200">{score}/100</span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-gradient-to-r from-emerald-500/40 via-amber-500/40 to-red-500/50">
        <div className="absolute top-1/2 h-3 w-1 -translate-y-1/2 rounded bg-white" style={{ left: `calc(${score}% - 2px)` }} />
      </div>
    </div>
  );
}

export function AnomalyScan({ symbol }: { symbol: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<HistoryBar[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const [ch, hi] = await Promise.all([loadChain(symbol).catch(() => ({ chain: [], spot: null, source: "" })), loadHistory(symbol).catch(() => ({ bars: [] }))]);
        if (cancelled) return;
        setChain(("chain" in ch ? ch.chain : []) as OptionContract[]);
        setSpot(("spot" in ch ? ch.spot : null) as number | null);
        setSource(("source" in ch ? ch.source : "") as string);
        setBars(("bars" in hi ? hi.bars : []) as HistoryBar[]);
        setState(("bars" in hi ? hi.bars : []).length ? "ok" : "empty");
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

  const r = useMemo(() => detectAnomalies(bars, chain, spot), [bars, chain, spot]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Performance Anomaly Detection · {symbol}</h2>
          <p className="text-xs text-neutral-500">statistical outliers vs trailing baseline · {r.sampleDays}d · src: {source}</p>
        </div>
        <ScoreMeter score={r.score} />
      </div>

      {state === "loading" && <Loading label="Scanning for anomalies…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No price history to scan." />}
      {state === "ok" && (
        <>
          <div className="mb-3">
            <span className={`rounded-full border px-3 py-1 text-sm font-medium ${stateChip[r.state]}`}>
              {r.state === "anomalous" ? "ANOMALOUS" : r.state === "watch" ? "WATCH" : "CALM"}
            </span>
          </div>

          {r.anomalies.length === 0 ? (
            <EmptyState label="No statistical anomalies — within normal ranges." />
          ) : (
            <div className="space-y-2">
              {r.anomalies.map((a) => (
                <div key={a.metric} className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-3 ${a.severity === "extreme" ? "border-l-red-500" : "border-l-amber-500"}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`font-mono ${dirColor(a.direction)}`}>{dirArrow(a.direction)}</span>
                      <span className="font-medium text-neutral-100">{a.metric}</span>
                      <span className="font-mono text-sm text-neutral-300">{a.value}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {a.z != null && <span className="font-mono text-xs text-neutral-400">{a.z >= 0 ? "+" : ""}{a.z.toFixed(1)}σ</span>}
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase ${sevChip[a.severity]}`}>{a.severity}</span>
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-neutral-400">{a.detail}</p>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 space-y-1">
            {r.notes.map((n) => (
              <p key={n} className="text-[11px] text-neutral-500">
                {n}
              </p>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
