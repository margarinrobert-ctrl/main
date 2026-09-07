"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { detectAnomalies, type AnomState, type Severity } from "@/lib/flow/anomaly";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sevChip: Record<Severity, string> = {
  extreme: "border-put/40 bg-put/10 text-put",
  elevated: "border-amber-400/40 bg-amber-400/10 text-amber-300",
};
const dirColor = (d: string) => (d === "up" ? "text-call" : d === "down" ? "text-put" : "text-neutral-300");
const dirArrow = (d: string) => (d === "up" ? "▲" : d === "down" ? "▼" : "•");
const stateChip: Record<AnomState, string> = {
  anomalous: "border-put/40 bg-put/10 text-put",
  watch: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  calm: "border-call/40 bg-call/10 text-call",
};

function ScoreMeter({ score }: { score: number }) {
  return (
    <div className="w-full max-w-[240px]">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="lbl">Anomaly score</span>
        <span className="font-mono text-xs tabular-nums text-neutral-200">{score}/100</span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-gradient-to-r from-call/40 via-amber-400/40 to-put/50">
        <div
          className="absolute top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.7)] transition-[left] duration-500"
          style={{ left: `calc(${score}% - 1.5px)` }}
        />
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
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="lbl mb-1">Anomaly detection</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
          <p className="mt-0.5 text-xs text-neutral-500">Statistical outliers vs trailing baseline · {r.sampleDays}d</p>
        </div>
        <ScoreMeter score={r.score} />
      </div>

      {state === "loading" && <Loading label="Loading anomaly scan…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No price history to scan." />}
      {state === "ok" && (
        <>
          <div className="mb-3">
            <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${stateChip[r.state]}`}>
              {r.state === "anomalous" ? "ANOMALOUS" : r.state === "watch" ? "WATCH" : "CALM"}
            </span>
          </div>

          {r.anomalies.length === 0 ? (
            <EmptyState label="No statistical anomalies — within normal ranges." />
          ) : (
            <div className="stagger space-y-2">
              {r.anomalies.map((a) => (
                <div key={a.metric} className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3.5 transition-colors hover:border-white/[0.14] hover:bg-white/[0.035] ${a.severity === "extreme" ? "border-l-put/80" : "border-l-amber-400/80"}`}>
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
                  <p className="mt-1.5 text-xs leading-relaxed text-neutral-400">{a.detail}</p>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 border-t border-white/[0.05] pt-3">
            <div className="lbl mb-1.5">Model notes</div>
            <div className="space-y-1">
              {r.notes.map((n) => (
                <p key={n} className="text-[11px] leading-relaxed text-neutral-500">
                  {n}
                </p>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
