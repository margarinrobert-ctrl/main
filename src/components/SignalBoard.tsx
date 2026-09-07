"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { buildSignals, type SignalCategory, type SignalSide, type TradeSignal } from "@/lib/flow/signals";
import { Chip, EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sideChip: Record<SignalSide, string> = {
  bullish: "border-call/30 bg-call/10 text-call",
  bearish: "border-put/30 bg-put/10 text-put",
  neutral: "border-white/10 bg-white/[0.03] text-neutral-300",
};
const sideBorder: Record<SignalSide, string> = {
  bullish: "border-l-call/80",
  bearish: "border-l-put/80",
  neutral: "border-l-accent-cyan/60",
};
const catChip: Record<SignalCategory, string> = {
  Directional: "border-white/10 bg-white/[0.03] text-neutral-300",
  Volatility: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  Regime: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  "Pin/Expiry": "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan",
  "Squeeze/Tail": "border-orange-400/30 bg-orange-400/10 text-orange-300",
  Skew: "border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-300",
};
const f2 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
const scoreStyle = (s: number) =>
  s >= 70
    ? "border-call/40 bg-call/10 text-call"
    : s >= 50
      ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
      : "border-white/10 bg-white/[0.03] text-neutral-300";

function BiasMeter({ score }: { score: number }) {
  const pct = (score + 100) / 2; // 0..100
  const label = score > 15 ? "Bullish" : score < -15 ? "Bearish" : "Neutral";
  const tone = score > 15 ? "text-call" : score < -15 ? "text-put" : "text-neutral-300";
  return (
    <div className="w-full max-w-[260px]">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="lbl">Composite bias</span>
        <span className={`font-mono text-xs ${tone}`}>
          {label} {score > 0 ? "+" : ""}
          {score}
        </span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-gradient-to-r from-put/50 via-white/10 to-call/50">
        <div className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-white/25" />
        <div
          className="absolute top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.7)]"
          style={{ left: `calc(${pct}% - 1.5px)` }}
        />
      </div>
      <div className="mt-1 flex justify-between">
        <span className="lbl">−100</span>
        <span className="lbl">+100</span>
      </div>
    </div>
  );
}

function Level({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="lbl">{label}</span>
      <span className={`font-mono text-xs ${tone ?? "text-neutral-200"}`}>{value}</span>
    </span>
  );
}

function SignalCard({ s }: { s: TradeSignal }) {
  return (
    <div
      className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3.5 transition-colors duration-200 hover:border-white/[0.12] hover:bg-white/[0.035] ${sideBorder[s.side]}`}
    >
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${catChip[s.category]}`}>{s.category}</span>
          <span className="font-medium text-neutral-100">{s.title}</span>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${sideChip[s.side]}`}>{s.side}</span>
        </div>
        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-xs ${scoreStyle(s.score)}`} title="Conviction (0–100)">
          {s.score}
        </span>
      </div>

      <p className="mb-1 text-xs leading-relaxed text-neutral-400">{s.thesis}</p>
      <p className="text-sm text-neutral-200">{s.trade}</p>

      <div className="mt-2.5 flex flex-wrap items-baseline gap-y-1 divide-x divide-white/5">
        {s.entry != null && (
          <span className="px-3 first:pl-0">
            <Level label="Entry" value={f2(s.entry)} tone="text-neutral-100" />
          </span>
        )}
        {s.targets.length > 0 && (
          <span className="px-3 first:pl-0">
            <Level label="Target" value={s.targets.map(f2).join(" / ")} tone="text-call" />
          </span>
        )}
        {s.stop != null && (
          <span className="px-3 first:pl-0">
            <Level label="Stop" value={f2(s.stop)} tone="text-put" />
          </span>
        )}
        <span className="px-3 first:pl-0">
          <Level label="Horizon" value={s.horizon} tone="text-neutral-300" />
        </span>
      </div>

      {s.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {s.tags.map((t) => (
            <span key={t} className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[10px] text-neutral-400">
              {t}
            </span>
          ))}
        </div>
      )}
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

  return (
    <div className="glass fade-up p-4">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <div className="lbl mb-1">Composite signal engine</div>
          <h2 className="display text-base text-neutral-50">Signal Board · {symbol}</h2>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <BiasMeter score={board.biasScore} />
          {board.regime !== "unknown" && (
            <Chip tone={board.regime === "long" ? "call" : "put"}>{board.regime === "long" ? "Long γ" : "Short γ"}</Chip>
          )}
        </div>
      </div>

      {state === "loading" && <Loading label="Loading signals…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for signals." />}
      {state === "ok" && (
        <>
          {board.signals.length === 0 ? (
            <EmptyState label="No signals above the conviction threshold." />
          ) : (
            <div className="stagger space-y-2">
              {board.signals.map((s) => (
                <SignalCard key={s.id} s={s} />
              ))}
            </div>
          )}
          {board.notes.length > 0 && (
            <div className="mt-4 border-t border-white/5 pt-3">
              <div className="lbl mb-1.5">Model notes</div>
              <div className="space-y-1">
                {board.notes.map((n) => (
                  <p key={n} className="text-[11px] leading-relaxed text-neutral-500">
                    {n}
                  </p>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
