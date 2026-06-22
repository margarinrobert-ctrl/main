"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { filterByExpiration } from "@/lib/flow/analytics";
import { anomalyIntel, type Band } from "@/lib/flow/anomalyPro";
import { readHistory, type GexSample } from "@/lib/gex-history";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "ok";

const bandTone: Record<Band, string> = {
  Weak: "border-neutral-500/40 bg-neutral-500/10 text-neutral-300",
  Moderate: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  Strong: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  Institutional: "border-orange-500/40 bg-orange-500/10 text-orange-300",
  Extreme: "border-red-500/40 bg-red-500/10 text-red-300",
};
const bandFill: Record<Band, string> = {
  Weak: "bg-neutral-400",
  Moderate: "bg-sky-400",
  Strong: "bg-amber-400",
  Institutional: "bg-orange-400",
  Extreme: "bg-red-500",
};
const riskTone: Record<string, string> = {
  Low: "text-emerald-300",
  Medium: "text-amber-300",
  High: "text-red-300",
};
const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

function Meter({ label, value, fill }: { label: string; value: number; fill: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-neutral-500">{label}</span>
        <span className="font-mono text-neutral-200">{value}/100</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${fill}`} style={{ width: `${Math.max(2, value)}%` }} />
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-sm ${tone ?? "text-neutral-100"}`}>{value}</div>
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
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Anomaly Intelligence · {symbol}</h2>
          <p className="text-xs text-neutral-500">
            ensemble detection · dealer-gamma classification · targets &amp; time-forecast ·{" "}
            {r.source === "intraday" ? "intraday session series" : r.source === "daily" ? "daily history" : "awaiting data"} · src: {source || "—"}
          </p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-sm font-medium ${bandTone[r.band]}`}>
          {r.band.toUpperCase()} · {r.strength}/100
        </span>
      </div>

      {state === "loading" && <Loading label="Computing anomaly intelligence…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "ok" && (
        <>
          {/* headline classification */}
          <div className="mb-4 rounded-lg border border-white/10 bg-white/[0.02] p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-neutral-100">{r.anomalyType}</span>
              <span className={`text-xs ${riskTone[r.riskRating] ?? "text-neutral-300"}`}>Risk: {r.riskRating}</span>
            </div>
            {/* bull / bear split */}
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-emerald-300">Bullish {r.bullish}%</span>
              {r.neutral && <span className="text-neutral-400">Neutral</span>}
              <span className="font-medium text-red-300">{r.bearish}% Bearish</span>
            </div>
            <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-white/10">
              <div className="h-full bg-emerald-500/80" style={{ width: `${r.bullish}%` }} />
              <div className="h-full bg-red-500/80" style={{ width: `${r.bearish}%` }} />
            </div>
            <p className="mt-2 text-xs text-neutral-400">{r.expectedEdge}</p>
          </div>

          {/* meters */}
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <Meter label="Anomaly strength" value={r.strength} fill={bandFill[r.band]} />
            <Meter label="Confidence" value={r.confidence} fill="bg-emerald-400" />
            <Meter label="Forecast window conf." value={r.timeForecast.confidence} fill="bg-sky-400" />
          </div>

          {/* ensemble */}
          <Section title="Statistical ensemble">
            <div className="space-y-1.5">
              {r.models.map((m) => (
                <div key={m.name} className="flex items-center gap-2 text-xs">
                  <span className="w-32 shrink-0 text-neutral-300">{m.name}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                    <div className={`h-full rounded-full ${m.vote >= 0.66 ? "bg-red-500" : m.vote >= 0.33 ? "bg-amber-400" : "bg-emerald-500/70"}`} style={{ width: `${Math.max(2, Math.round(m.vote * 100))}%` }} />
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
                    <div key={t.label} className="flex items-center justify-between rounded border border-white/10 px-3 py-1.5 text-sm">
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
                  <span className={f.ok ? "text-emerald-400" : "text-neutral-600"}>{f.ok ? "✓" : "○"}</span>
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
                    <span className={`w-16 shrink-0 font-mono ${r.anomalyLevel != null && l.price >= r.anomalyLevel ? "text-emerald-300" : "text-red-300"}`}>{num(l.price)}</span>
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
            <p className="mt-3 rounded border border-white/10 bg-white/[0.02] p-2 text-xs text-neutral-300">
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
            <div className="flex items-center gap-2 pt-1">
              <button onClick={() => setShowJson((s) => !s)} className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700">
                {showJson ? "Hide" : "Show"} JSON output
              </button>
              {showJson && (
                <button onClick={copyJson} className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700">
                  {copied ? "Copied ✓" : "Copy"}
                </button>
              )}
            </div>
            {showJson && (
              <pre className="mt-2 max-h-[320px] overflow-auto rounded-lg border border-white/10 bg-black/50 p-3 text-[11px] leading-relaxed text-neutral-200">
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
    <div className="mt-4">
      <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">{title}</div>
      {children}
    </div>
  );
}
