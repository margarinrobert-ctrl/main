"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { pullServerData } from "@/lib/client-data";
import { readHistory } from "@/lib/gex-history";
import { readJournal, writeJournal, type PredictionRecord } from "@/lib/intel/journal";
import { open, resolved, resolveForSymbol } from "@/lib/intel/resolve";
import {
  breakdown,
  calibration,
  confidenceBand,
  edgeDecay,
  equityCurve,
  featureDrift,
  featureImportance,
  healthState,
  rankModels,
  rollingEdge,
  summarize,
  type Group,
  type HealthState,
} from "@/lib/intel/performance";
import { ensembleForecast } from "@/lib/intel/ensemble";
import { recommend, type Severity } from "@/lib/intel/recommend";
import { walkForwardThreshold, whatIfRules } from "@/lib/intel/experiment";
import type { IntelDir } from "@/lib/intel/journal";
import { EmptyState } from "./states";

const healthTone: Record<HealthState, string> = {
  improving: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  stable: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  degrading: "border-red-500/40 bg-red-500/10 text-red-300",
  insufficient: "border-neutral-500/40 bg-neutral-500/10 text-neutral-300",
};
const sevTone: Record<Severity, string> = {
  critical: "border-l-red-500",
  warn: "border-l-amber-500",
  info: "border-l-sky-500",
};
const hhmm = (t: number) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const sp = (x: number | null | undefined, d = 2) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(d)}%`);
const f2 = (x: number | null | undefined) => (x == null ? "—" : x.toFixed(2));
const dirChip = (d: IntelDir) =>
  d === "bullish" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : d === "bearish" ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-sky-500/40 bg-sky-500/10 text-sky-300";
const dirLabel = (d: IntelDir) => (d === "bullish" ? "▲ BULLISH" : d === "bearish" ? "▼ BEARISH" : "■ NEUTRAL");
const dirDot = (d: IntelDir) => (d === "bullish" ? "bg-emerald-400" : d === "bearish" ? "bg-red-400" : "bg-neutral-400");

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-sm ${tone ?? "text-neutral-100"}`}>{value}</div>
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <div className="text-xs uppercase tracking-wide text-neutral-500">{title}</div>
        {hint && <div className="text-[10px] text-neutral-600">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function GroupTable({ groups }: { groups: Group[] }) {
  if (!groups.length) return <p className="text-xs text-neutral-500">Not enough resolved calls in any bucket yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-1 pr-3 font-medium">Bucket</th>
            <th className="px-3 font-medium">n</th>
            <th className="px-3 font-medium">Hit</th>
            <th className="px-3 font-medium">Expectancy</th>
            <th className="px-3 font-medium">Sharpe</th>
            <th className="px-3 font-medium">PF</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {groups.map((g) => (
            <tr key={g.key} className="border-t border-white/5">
              <td className="py-1 pr-3 font-sans text-neutral-200">{g.key}</td>
              <td className="px-3 text-neutral-400">{g.summary.n}</td>
              <td className="px-3 text-neutral-300">{g.summary.hitRate != null ? `${Math.round(g.summary.hitRate * 100)}%` : "—"}</td>
              <td className={`px-3 ${(g.summary.expectancy ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"}`}>{sp(g.summary.expectancy)}</td>
              <td className="px-3 text-neutral-300">{f2(g.summary.sharpe)}</td>
              <td className="px-3 text-neutral-300">{g.summary.profitFactor === Infinity ? "∞" : f2(g.summary.profitFactor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function IntelLab({ symbol }: { symbol: string }) {
  const sym = symbol.toUpperCase();
  const [all, setAll] = useState(false);
  const [tick, setTick] = useState(0);
  const [showJson, setShowJson] = useState(false);
  const [storeMode, setStoreMode] = useState<string | null>(null);

  // pull durable server-collected data, merge locally, then resolve matured predictions and re-read.
  const refresh = useCallback(async () => {
    try {
      const r = await pullServerData(sym);
      setStoreMode(r.storeMode);
    } catch {
      /* offline / no server store reachable — local data still works */
    }
    const journal = readJournal();
    const next = resolveForSymbol(journal, sym, readHistory(sym), Date.now());
    if (next !== journal) writeJournal(next);
    setTick((t) => t + 1);
  }, [sym]);

  useEffect(() => {
    refresh();
    const ms = Math.max(15_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 30_000) || 30_000);
    const id = setInterval(refresh, ms);
    return () => clearInterval(id);
  }, [refresh]);

  const records = useMemo(() => {
    void tick;
    const j = readJournal();
    return all ? j : j.filter((r) => r.symbol === sym);
  }, [all, sym, tick]);

  const a = useMemo(() => {
    const res = resolved(records);
    return {
      res,
      openN: open(records).length,
      perf: summarize(records),
      health: healthState(records),
      decay: edgeDecay(records),
      roll: rollingEdge(records, 20).map((p) => ({ ...p, label: hhmm(p.t) })),
      models: rankModels(records, 5).length ? rankModels(records, 5) : breakdown(records, (r) => r.model, 1),
      byRegime: breakdown(records, (r) => `${r.regime}-γ`, 1),
      byVol: breakdown(records, (r) => r.volRegime, 1),
      byConf: breakdown(records, (r) => confidenceBand(r.confidence), 1),
      byDir: breakdown(records, (r) => r.direction, 1),
      cal: calibration(records),
      feats: featureImportance(records),
      drift: featureDrift(records),
      recs: recommend(records),
      wf: walkForwardThreshold(records),
      whatif: whatIfRules(records),
      ensemble: ensembleForecast(records),
      equity: equityCurve(records).map((p) => ({ ...p, label: hhmm(p.t) })),
    };
  }, [records]);

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(records, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url;
    el.download = `intel_${all ? "ALL" : sym}.json`;
    el.click();
    URL.revokeObjectURL(url);
  };

  const maxCorr = Math.max(0.0001, ...a.feats.map((f) => Math.abs(f.corr)));

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Performance Intelligence · {all ? "all tickers" : sym}</h2>
          <p className="text-xs text-neutral-500">self-scoring journal · {records.length} predictions · {a.res.length} resolved · {a.openN} open</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full border px-3 py-1 text-sm font-medium ${healthTone[a.health]}`}>{a.health.toUpperCase()}</span>
          <button onClick={() => setAll((v) => !v)} className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700">
            {all ? "This ticker" : "All tickers"}
          </button>
        </div>
      </div>

      {storeMode === "kv" ? (
        <p className="mb-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-[11px] text-emerald-300">
          Server collection ON — durable KV store connected. With a scheduler hitting <code>/api/collect</code>, history accrues 24/7 even when this site is closed.
        </p>
      ) : storeMode === "git" ? (
        <p className="mb-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-[11px] text-emerald-300">
          Server collection via GitHub Actions (git store) — the scheduled job records + resolves predictions to the <code>intel-data</code> branch 24/7, even when this site is closed. Enable the workflow on your default branch to start it. See <code>COLLECTION.md</code>.
        </p>
      ) : storeMode === "memory" ? (
        <p className="mb-3 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300">
          Server collection is ephemeral — predictions persist only in this browser. To collect 24/7 while closed, enable the GitHub Actions collector (no signup) or wire a KV store. See <code>COLLECTION.md</code>.
        </p>
      ) : null}

      {records.length === 0 ? (
        <EmptyState label="No predictions journaled yet. Open a ticker tab and leave it running — the collector records every anomaly / signal / MM-hedge call and scores it against the price that follows." />
      ) : (
        <>
          {/* AI ensemble forecast — live blend of each engine's latest call, weighted by its realised track record */}
          {a.ensemble.available && (
            <div
              className={`mb-4 rounded-lg border border-white/10 border-l-4 bg-white/[0.02] p-4 ${
                a.ensemble.direction === "bullish" ? "border-l-emerald-500" : a.ensemble.direction === "bearish" ? "border-l-red-500" : "border-l-sky-500"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-[11px] uppercase tracking-wide text-neutral-400">AI ensemble forecast</span>
                  <span className={`rounded-full border px-3 py-1 text-sm font-semibold ${dirChip(a.ensemble.direction)}`}>{dirLabel(a.ensemble.direction)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
                  <span className="rounded border border-white/10 px-2 py-1 text-neutral-200">P(up) {Math.round(a.ensemble.pUp * 100)}%</span>
                  <span className="rounded border border-white/10 px-2 py-1 text-neutral-200">conf {a.ensemble.confidence}%</span>
                  <span className="rounded border border-white/10 px-2 py-1 text-neutral-200">agree {Math.round(a.ensemble.agreement * 100)}%</span>
                  {a.ensemble.kelly != null && <span className="rounded border border-white/10 px-2 py-1 text-emerald-300">¼-Kelly {(a.ensemble.kelly * 100).toFixed(1)}%</span>}
                </div>
              </div>
              <div className="mt-3 space-y-1.5">
                {a.ensemble.votes.map((v) => (
                  <div key={v.source} className="flex items-center gap-2 text-xs">
                    <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${dirDot(v.direction)}`} />
                    <span className="w-32 shrink-0 truncate text-neutral-300" title={v.source}>{v.source}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-neutral-200/70" style={{ width: `${Math.round(v.weight * 100)}%` }} />
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-neutral-400">{Math.round(v.weight * 100)}%</span>
                    <span className="hidden w-28 shrink-0 text-right font-mono text-neutral-500 sm:inline">{v.edge != null ? `${sp(v.edge)} edge` : "new"} · n{v.n}</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-neutral-500">{a.ensemble.note} Weighted blend of each engine&apos;s latest call by its realised edge &amp; freshness — a directional probability, not a guarantee.</p>
            </div>
          )}

          {/* headline metrics */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Hit rate" value={a.perf.hitRate != null ? `${Math.round(a.perf.hitRate * 100)}%` : "—"} tone={(a.perf.hitRate ?? 0) >= 0.5 ? "text-emerald-300" : "text-red-300"} />
            <Stat label="Hit-rate 95% CI" value={a.perf.ci ? `${Math.round(a.perf.ci.lo * 100)}–${Math.round(a.perf.ci.hi * 100)}%` : "—"} />
            <Stat label="Expectancy / call" value={sp(a.perf.expectancy)} tone={(a.perf.expectancy ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"} />
            <Stat label="Sharpe (per call)" value={f2(a.perf.sharpe)} />
            <Stat label="Sortino" value={f2(a.perf.sortino)} tone={(a.perf.sortino ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"} />
            <Stat label="Profit factor" value={a.perf.profitFactor === Infinity ? "∞" : f2(a.perf.profitFactor)} />
            <Stat label="Max drawdown" value={a.perf.maxDrawdown != null ? `−${a.perf.maxDrawdown.toFixed(2)}%` : "—"} tone="text-red-300" />
            <Stat label="Brier (cal.)" value={a.perf.brier != null ? a.perf.brier.toFixed(3) : "—"} />
            <Stat label="Kelly (full)" value={a.perf.kelly != null ? `${(a.perf.kelly * 100).toFixed(0)}%` : "—"} />
          </div>

          {/* recommendations first — the actionable layer */}
          <Section title="Recommendations" hint="derived from resolved outcomes">
            <div className="space-y-2">
              {a.recs.map((rec) => (
                <div key={rec.id} className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-3 ${sevTone[rec.severity]}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium text-neutral-100">{rec.title}</span>
                    <span className="text-[10px] uppercase tracking-wide text-neutral-500">{rec.severity} · conf {rec.confidence}%</span>
                  </div>
                  <p className="mt-1 text-xs text-neutral-300">{rec.detail}</p>
                  <p className="mt-1 font-mono text-[11px] text-neutral-500">{rec.evidence}</p>
                  <p className="mt-1 text-xs text-sky-300/90">→ {rec.action}</p>
                </div>
              ))}
            </div>
          </Section>

          {/* edge over time */}
          {a.roll.length >= 3 && (
            <Section title="Edge over time" hint="rolling mean directional return (last 20 calls)">
              <div className="h-[200px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={a.roll} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                    <defs>
                      <linearGradient id="edgePos" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#34d399" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="#34d399" stopOpacity={0.03} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#1f1f1f" />
                    <XAxis dataKey="label" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" minTickGap={40} />
                    <YAxis tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={48} tickFormatter={(v) => `${v}%`} />
                    <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }} formatter={(v: number | string, n) => [n === "edge" ? `${Number(v).toFixed(2)}%` : `${Math.round(Number(v) * 100)}%`, n === "edge" ? "edge" : "hit rate"]} />
                    <ReferenceLine y={0} stroke="#525252" strokeDasharray="3 3" />
                    <Area type="monotone" dataKey="edge" stroke="#34d399" strokeWidth={1.6} fill="url(#edgePos)" isAnimationActive={false} />
                    <Line type="monotone" dataKey="hitRate" stroke="#38bdf8" strokeWidth={1.2} dot={false} yAxisId="hr" isAnimationActive={false} />
                    <YAxis yAxisId="hr" orientation="right" domain={[0, 1]} hide />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Section>
          )}

          {/* cumulative edge / equity curve with running drawdown */}
          {a.equity.length >= 3 && (
            <Section title="Cumulative edge (equity curve)" hint="Σ directional return · resolved order">
              <div className="h-[180px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={a.equity} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                    <defs>
                      <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.03} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#1f1f1f" />
                    <XAxis dataKey="label" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" minTickGap={40} />
                    <YAxis tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={48} tickFormatter={(v) => `${v}%`} />
                    <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }} formatter={(v: number | string, n) => [`${Number(v).toFixed(2)}%`, n === "equity" ? "cum. edge" : "drawdown"]} />
                    <ReferenceLine y={0} stroke="#525252" strokeDasharray="3 3" />
                    <Area type="monotone" dataKey="equity" stroke="#a78bfa" strokeWidth={1.6} fill="url(#eqFill)" isAnimationActive={false} />
                    <Area type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={1} fill="#ef4444" fillOpacity={0.12} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Section>
          )}

          {/* model rankings + regime/vol breakdowns */}
          <Section title="Model rankings" hint="ranked by per-call Sharpe">
            <GroupTable groups={a.models} />
          </Section>
          <div className="grid gap-4 md:grid-cols-2">
            <Section title="By dealer-gamma regime">
              <GroupTable groups={a.byRegime} />
            </Section>
            <Section title="By volatility regime">
              <GroupTable groups={a.byVol} />
            </Section>
            <Section title="By confidence band">
              <GroupTable groups={a.byConf} />
            </Section>
            <Section title="By direction">
              <GroupTable groups={a.byDir} />
            </Section>
          </div>

          {/* calibration */}
          {a.cal.bins.length > 0 && (
            <Section title="Calibration" hint={a.cal.error != null ? `mean error ${(a.cal.error * 100).toFixed(0)} pts` : undefined}>
              <div className="space-y-1.5">
                {a.cal.bins.map((b) => (
                  <div key={b.label} className="flex items-center gap-2 text-xs">
                    <span className="w-16 shrink-0 text-neutral-300">{b.label}</span>
                    <div className="relative h-3 flex-1 rounded-full bg-white/10">
                      <div className="absolute top-0 h-3 w-0.5 bg-neutral-300" style={{ left: `${b.predicted}%` }} title={`predicted ${Math.round(b.predicted)}%`} />
                      <div className="h-3 rounded-full bg-sky-500/50" style={{ width: `${b.realized}%` }} />
                    </div>
                    <span className="w-28 shrink-0 text-right font-mono text-neutral-400">{Math.round(b.realized)}% real · n{b.n}</span>
                  </div>
                ))}
                <p className="text-[10px] text-neutral-600">bar = realised hit-rate · tick = stated confidence. Aligned = well-calibrated.</p>
              </div>
            </Section>
          )}

          {/* feature importance + drift */}
          {a.feats.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              <Section title="Feature importance" hint="assoc. with directional return">
                <div className="space-y-1.5">
                  {a.feats.slice(0, 8).map((f) => (
                    <div key={f.feature} className="flex items-center gap-2 text-xs">
                      <span className="w-28 shrink-0 truncate text-neutral-300" title={f.feature}>{f.feature}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                        <div className={`h-full rounded-full ${f.corr >= 0 ? "bg-emerald-500/70" : "bg-red-500/70"}`} style={{ width: `${Math.round((Math.abs(f.corr) / maxCorr) * 100)}%` }} />
                      </div>
                      <span className="w-12 shrink-0 text-right font-mono text-neutral-400">{f.corr >= 0 ? "+" : ""}{f.corr.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </Section>
              {a.drift.length > 0 && (
                <Section title="Feature drift" hint="older vs recent journal">
                  <div className="space-y-1.5 text-xs">
                    {a.drift.slice(0, 6).map((d) => (
                      <div key={d.feature} className="flex items-center justify-between gap-2">
                        <span className="text-neutral-300">{d.feature}</span>
                        <span className="font-mono text-neutral-400">
                          {d.baseline.toFixed(1)} → {d.recent.toFixed(1)}
                          <span className={`ml-2 ${d.drifting ? "text-amber-300" : "text-neutral-600"}`}>{d.z >= 0 ? "+" : ""}{d.z.toFixed(1)}σ</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </Section>
              )}
            </div>
          )}

          {/* optimisation: walk-forward + what-ifs */}
          <Section title="Optimisation (walk-forward, out-of-sample)" hint="evaluation only — not auto-applied">
            <div className="mb-2 rounded border border-white/10 bg-white/[0.02] p-3 text-xs">
              {a.wf.ok ? (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label="Best conf. cut-off" value={a.wf.bestThreshold != null ? `≥ ${a.wf.bestThreshold}` : "—"} />
                  <Stat label="Train expectancy" value={sp(a.wf.trainExpectancy)} />
                  <Stat label="Test (out-of-sample)" value={sp(a.wf.testExpectancy)} tone={(a.wf.testExpectancy ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"} />
                  <Stat label="vs take-all" value={sp(a.wf.improvement)} tone={(a.wf.improvement ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"} />
                </div>
              ) : (
                <p className="text-neutral-500">{a.wf.note}</p>
              )}
              {a.wf.ok && <p className="mt-2 text-[11px] text-neutral-500">{a.wf.note}</p>}
            </div>
            {a.whatif.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-neutral-500">
                    <tr>
                      <th className="py-1 pr-3 font-medium">Decision filter</th>
                      <th className="px-3 font-medium">n</th>
                      <th className="px-3 font-medium">Hit</th>
                      <th className="px-3 font-medium">Expectancy</th>
                      <th className="px-3 font-medium">Δ vs all</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {a.whatif.map((w) => (
                      <tr key={w.rule} className="border-t border-white/5">
                        <td className="py-1 pr-3 font-sans text-neutral-200">{w.rule}</td>
                        <td className="px-3 text-neutral-400">{w.n}</td>
                        <td className="px-3 text-neutral-300">{w.hitRate != null ? `${Math.round(w.hitRate * 100)}%` : "—"}</td>
                        <td className={`px-3 ${(w.expectancy ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"}`}>{sp(w.expectancy)}</td>
                        <td className={`px-3 ${(w.deltaVsAll ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"}`}>{sp(w.deltaVsAll)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* report / export */}
          <div className="mt-5 flex items-center gap-2 border-t border-white/10 pt-3">
            <button onClick={exportJson} className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700">Export journal (JSON)</button>
            <button onClick={() => setShowJson((s) => !s)} className="rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700">{showJson ? "Hide" : "Show"} recent records</button>
          </div>
          {showJson && (
            <pre className="mt-2 max-h-[320px] overflow-auto rounded-lg border border-white/10 bg-black/50 p-3 text-[10px] leading-relaxed text-neutral-200">
              <code>{JSON.stringify(records.slice(-25), null, 2)}</code>
            </pre>
          )}

          <div className="mt-4 space-y-1 border-t border-white/10 pt-3">
            <p className="text-[11px] text-neutral-500">Predictions are journaled locally (your browser) and scored against the recorded ~30–60s session spot series — real outcomes, no simulation. Short-horizon (anomaly) calls resolve within a session; longer-horizon calls resolve only while tabs stay open.</p>
            <p className="text-[11px] text-neutral-500">Walk-forward / what-ifs are out-of-sample evaluations on recorded history, not auto-applied parameter changes. Feature importance is association on the recorded sample, not proven causation. Educational — not financial advice.</p>
          </div>
        </>
      )}
    </div>
  );
}
