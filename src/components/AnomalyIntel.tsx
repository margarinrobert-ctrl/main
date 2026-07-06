"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { filterByExpiration } from "@/lib/flow/analytics";
import { anomalyIntel, type Band } from "@/lib/flow/anomalyPro";
import { readHistory, type GexSample } from "@/lib/gex-history";
import { ErrorState, Loading, Stat } from "./states";

type ViewState = "loading" | "error" | "ok";

const bandTone: Record<Band, string> = {
  Weak: "border-white/10 bg-white/[0.03] text-neutral-300",
  Moderate: "border-sky-400/40 bg-sky-400/10 text-sky-300",
  Strong: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  Institutional: "border-amber-400/50 bg-amber-400/15 text-amber-200",
  Extreme: "border-put/40 bg-put/10 text-put",
};
const bandFill: Record<Band, string> = {
  Weak: "bg-neutral-400",
  Moderate: "bg-sky-400",
  Strong: "bg-amber-400",
  Institutional: "bg-amber-300",
  Extreme: "bg-put",
};
const riskTone: Record<string, string> = {
  Low: "text-call",
  Medium: "text-amber-300",
  High: "text-put",
};
const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

function Meter({ label, value, fill }: { label: string; value: number; fill: string }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="lbl">{label}</span>
        <span className="font-mono text-xs tabular-nums text-neutral-200">{value}/100</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full transition-[width] duration-500 ${fill}`} style={{ width: `${Math.max(2, value)}%` }} />
      </div>
    </div>
  );
}

export function AnomalyIntel({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<HistoryBar[]>([]);
  const [samples, setSamples] = useState<GexSample[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [showJson, setShowJson] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ch, hi] = await Promise.all([
        loadChain(symbol).catch(() => ({ chain: [], spot: null, source: "" })),
        loadHistory(symbol).catch(() => ({ bars: [] as HistoryBar[] })),
      ]);
      setChain(("chain" in ch ? ch.chain : []) as OptionContract[]);
      setSpot(("spot" in ch ? ch.spot : null) as number | null);
      setSource(("source" in ch ? ch.source : "") as string);
      setBars(("bars" in hi ? hi.bars : []) as HistoryBar[]);
      setSamples(readHistory(symbol));
      setState("ok");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
  }, [symbol]);

  useEffect(() => {
    setState("loading");
    load();
    const ms = Math.max(15_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 30_000) || 30_000);
    const id = setInterval(load, ms);
    return () => clearInterval(id);
  }, [load]);

  const scoped = useMemo(() => filterByExpiration(chain, exp), [chain, exp]);
  const r = useMemo(() => anomalyIntel(symbol, scoped, spot, bars, samples), [symbol, scoped, spot, bars, samples]);

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(r.json);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked */
    }
  };

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="lbl mb-1">Anomaly intelligence</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
          <p className="mt-0.5 text-xs text-neutral-500">
            Ensemble detection · dealer-gamma classification · targets &amp; time-forecast ·{" "}
            {r.source === "intraday" ? "intraday session series" : r.source === "daily" ? "daily history" : "awaiting data"}
          </p>
        </div>
        <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${bandTone[r.band]}`}>
          {r.band} · {r.strength}/100
        </span>
      </div>

      {state === "loading" && <Loading label="Loading anomaly intelligence…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "ok" && (
        <>
          {/* headline classification */}
          <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-neutral-100">{r.anomalyType}</span>
              <span className={`text-xs font-medium ${riskTone[r.riskRating] ?? "text-neutral-300"}`}>Risk: {r.riskRating}</span>
            </div>
            {/* bull / bear split */}
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="font-medium text-call">Bullish {r.bullish}%</span>
              {r.neutral && <span className="text-neutral-400">Neutral</span>}
              <span className="font-medium text-put">{r.bearish}% Bearish</span>
            </div>
            <div className="flex h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div className="h-full bg-call/80 transition-[width] duration-500" style={{ width: `${r.bullish}%` }} />
              <div className="h-full bg-put/80 transition-[width] duration-500" style={{ width: `${r.bearish}%` }} />
            </div>
            <p className="mt-2 text-xs leading-relaxed text-neutral-400">{r.expectedEdge}</p>
          </div>

          {/* meters */}
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <Meter label="Anomaly strength" value={r.strength} fill={bandFill[r.band]} />
            <Meter label="Confidence" value={r.confidence} fill="bg-call" />
            <Meter label="Forecast window conf." value={r.timeForecast.confidence} fill="bg-sky-400" />
          </div>

          {/* ensemble */}
          <Section title="Statistical ensemble">
            <div className="space-y-1.5">
              {r.models.map((m) => (
                <div key={m.name} className="flex items-center gap-2 text-xs">
                  <span className="w-32 shrink-0 text-neutral-300">{m.name}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                    <div className={`h-full rounded-full ${m.vote >= 0.66 ? "bg-put" : m.vote >= 0.33 ? "bg-amber-400" : "bg-call/70"}`} style={{ width: `${Math.max(2, Math.round(m.vote * 100))}%` }} />
                  </div>
                  <span className="w-10 shrink-0 text-right font-mono text-neutral-400">{Math.round(m.vote * 100)}%</span>
                  <span className="hidden w-44 shrink-0 truncate text-neutral-500 sm:inline" title={m.detail}>
                    {m.detail}
                  </span>
                </div>
              ))}
              {r.models.length === 0 && <p className="text-xs text-neutral-500">Not enough samples yet — keep a ticker tab open to record an intraday series, or this scores off daily history.</p>}
            </div>
          </Section>

          {/* targets + time forecast */}
          <div className="grid gap-4 md:grid-cols-2">
            <Section title="Price targets">
              <div className="mb-2 grid grid-cols-2 gap-2">
                <Stat label="Anomaly level" value={r.anomalyLevel == null ? "—" : num(r.anomalyLevel)} />
                <Stat label="Expected move (1σ)" value={r.expectedMove == null ? "—" : `±${num(r.expectedMove)}`} />
              </div>
              {r.targets.length === 0 ? (
                <p className="text-xs text-neutral-500">No directional targets — read is neutral or data is thin.</p>
              ) : (
                <div className="space-y-1.5">
                  {r.targets.map((t) => (
                    <div key={t.label} className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.015] px-3 py-2 text-sm">
                      <span className="text-neutral-400">{t.label}</span>
                      <span className="font-mono text-neutral-100">{num(t.price)}</span>
                      <span className="text-xs text-neutral-500">{t.kind}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            <Section title={`Time forecast · ${r.timeForecast.window} · ${r.timeForecast.duration}`}>
              <div className="space-y-1.5">
                {r.timeForecast.probs.map((p) => (
                  <div key={p.h} className="flex items-center gap-2 text-xs">
                    <span className="w-8 shrink-0 text-neutral-300">{p.h}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                      <div className={`h-full rounded-full ${p.h === r.timeForecast.window ? "bg-sky-400" : "bg-sky-500/40"}`} style={{ width: `${Math.max(2, p.p)}%` }} />
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-neutral-400">{p.p}%</span>
                  </div>
                ))}
              </div>
            </Section>
          </div>

          {/* quant factors */}
          <Section title="Quant factors">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {Object.entries(r.quant).map(([k, val]) => (
                <Stat key={k} label={k} value={val} />
              ))}
            </div>
          </Section>

          {/* confidence factors */}
          <Section title="Confidence factors">
            <div className="space-y-1.5">
              {r.confidenceFactors.map((f) => (
                <div key={f.label} className="flex items-start gap-2 text-xs">
                  <span className={f.ok ? "text-call" : "text-neutral-600"}>{f.ok ? "✓" : "○"}</span>
                  <span className="w-40 shrink-0 text-neutral-300">{f.label}</span>
                  <span className="text-neutral-500">{f.detail}</span>
                </div>
              ))}
            </div>
          </Section>

          {/* ranked levels */}
          {r.levels.length > 0 && (
            <Section title="Key levels (ranked by proximity)">
              <div className="space-y-1.5">
                {r.levels.map((l) => (
                  <div key={`${l.kind}-${l.price}`} className="flex items-center gap-2 text-xs">
                    <span className="w-44 shrink-0 text-neutral-300">{l.kind}</span>
                    <span className={`w-16 shrink-0 font-mono tabular-nums ${r.anomalyLevel != null && l.price >= r.anomalyLevel ? "text-call" : "text-put"}`}>{num(l.price)}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-neutral-400" style={{ width: `${Math.max(3, Math.round(l.strength * 100))}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* explainability */}
          <Section title="Why — explainable read">
            <ul className="space-y-1 text-xs text-neutral-300">
              {r.why.map((w, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-neutral-600">›</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 rounded-lg border border-accent/20 bg-accent/[0.04] p-3 text-xs leading-relaxed text-neutral-300">
              <span className="font-medium text-neutral-100">Institutional read: </span>
              {r.institutional}
            </p>
          </Section>

          {/* methodology + json */}
          <div className="mt-4 space-y-1 border-t border-white/10 pt-3">
            {r.methodology.map((m) => (
              <p key={m} className="text-[11px] text-neutral-500">
                {m}
              </p>
            ))}
            <div className="flex items-center gap-2 pt-2">
              <button onClick={() => setShowJson((s) => !s)} className="btn !px-3 !py-1.5 !text-xs" aria-expanded={showJson}>
                {showJson ? "Hide" : "Show"} JSON output
              </button>
              {showJson && (
                <button onClick={copyJson} className="btn !px-3 !py-1.5 !text-xs">
                  {copied ? "Copied ✓" : "Copy"}
                </button>
              )}
            </div>
            {showJson && (
              <pre className="mt-2 max-h-[320px] overflow-auto rounded-xl border border-white/10 bg-[#07080c] p-3.5 text-[11px] leading-relaxed text-neutral-200">
                <code>{r.json}</code>
              </pre>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4 border-t border-white/[0.05] pt-3">
      <div className="lbl mb-2">{title}</div>
      {children}
    </div>
  );
}
