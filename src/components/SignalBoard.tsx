"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { buildSignals, type SignalCategory, type SignalSide, type TradeSignal } from "@/lib/flow/signals";
import { EdgeBadge } from "./EdgeBadge";
import { EmptyState, ErrorState, Loading } from "./states";
import { useLearnedProfile } from "./useLearnedProfile";

type ViewState = "loading" | "error" | "empty" | "ok";

const sideChip: Record<SignalSide, string> = {
  bullish: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  bearish: "border-red-500/40 bg-red-500/10 text-red-300",
  neutral: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};
const sideBorder: Record<SignalSide, string> = {
  bullish: "border-l-emerald-500",
  bearish: "border-l-red-500",
  neutral: "border-l-sky-500",
};
const catChip: Record<SignalCategory, string> = {
  Directional: "bg-white/10 text-neutral-200",
  Volatility: "bg-amber-500/15 text-amber-300",
  Regime: "bg-violet-500/15 text-violet-300",
  "Pin/Expiry": "bg-cyan-500/15 text-cyan-300",
  "Squeeze/Tail": "bg-orange-500/15 text-orange-300",
  Skew: "bg-fuchsia-500/15 text-fuchsia-300",
};
const f2 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
const scoreStyle = (s: number) => (s >= 70 ? "bg-emerald-900 text-emerald-200" : s >= 50 ? "bg-amber-900 text-amber-200" : "bg-neutral-800 text-neutral-300");

function BiasMeter({ score }: { score: number }) {
  const pct = (score + 100) / 2; // 0..100
  const label = score > 15 ? "Bullish" : score < -15 ? "Bearish" : "Neutral";
  const color = score > 15 ? "text-emerald-300" : score < -15 ? "text-red-300" : "text-sky-300";
  return (
    <div className="min-w-[200px] flex-1">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-neutral-500">Composite bias</span>
        <span className={`font-mono ${color}`}>
          {label} {score > 0 ? "+" : ""}
          {score}
        </span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-gradient-to-r from-red-500/40 via-neutral-600/40 to-emerald-500/40">
        <div className="absolute top-1/2 h-3 w-1 -translate-y-1/2 rounded bg-white" style={{ left: `calc(${pct}% - 2px)` }} />
        <div className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-white/30" />
      </div>
    </div>
  );
}

function Level({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</span>
      <span className={`font-mono ${tone ?? "text-neutral-200"}`}>{value}</span>
    </span>
  );
}

function SignalCard({ s }: { s: TradeSignal }) {
  return (
    <div className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-3 ${sideBorder[s.side]}`}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${catChip[s.category]}`}>{s.category}</span>
          <span className="font-medium text-neutral-100">{s.title}</span>
          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${sideChip[s.side]}`}>{s.side}</span>
        </div>
        <span className={`inline-block rounded px-2 py-0.5 font-mono text-xs ${scoreStyle(s.score)}`} title="Conviction (0–100)">
          {s.score}
        </span>
      </div>

      <p className="mb-1 text-xs text-neutral-400">{s.thesis}</p>
      <p className="mb-2 text-sm text-neutral-200">{s.trade}</p>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {s.entry != null && <Level label="Entry" value={f2(s.entry)} tone="text-neutral-100" />}
        {s.targets.length > 0 && <Level label="Target" value={s.targets.map(f2).join(" / ")} tone="text-emerald-300" />}
        {s.stop != null && <Level label="Stop" value={f2(s.stop)} tone="text-red-300" />}
        <Level label="Horizon" value={s.horizon} tone="text-neutral-300" />
        {s.tags.map((t) => (
          <span key={t} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-neutral-400">
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

export function SignalBoard({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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
        const [ch, hi] = await Promise.all([loadChain(symbol), loadHistory(symbol).catch(() => ({ bars: [] }))]);
        if (cancelled) return;
        setChain(ch.chain);
        setSpot(ch.spot);
        setSource(ch.source);
        setBars(("bars" in hi ? hi.bars : []) as HistoryBar[]);
        setState(ch.chain.length ? "ok" : "empty");
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

  const board = useMemo(() => buildSignals(chain, spot, bars, exp), [chain, spot, bars, exp]);
  const profile = useLearnedProfile();

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">Signal Board · {symbol}</h2>
          <EdgeBadge profile={profile} source="signals" confidence={board.signals[0]?.score ?? null} />
        </div>
        <BiasMeter score={board.biasScore} />
        <span className="text-xs text-neutral-500">
          {board.regime !== "unknown" ? `${board.regime}-γ` : ""} · src: {source}
        </span>
      </div>

      {state === "loading" && <Loading label="Computing signals…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for signals." />}
      {state === "ok" && (
        <>
          {board.signals.length === 0 ? (
            <EmptyState label="No actionable signals right now." />
          ) : (
            <div className="space-y-2">
              {board.signals.map((s) => (
                <SignalCard key={s.id} s={s} />
              ))}
            </div>
          )}
          <div className="mt-4 space-y-1">
            {board.notes.map((n) => (
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
