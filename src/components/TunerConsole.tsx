"use client";

/**
 * The tuning console: change a knob, see the result.
 *
 * Everything runs in the browser, in a worker. That is not a limitation worked around — it is the
 * only design that fits the constraints. Bar files are large and often licensed, so `data/*.csv`
 * is git-ignored and never reaches the server; and the app also builds as a static export, where
 * there is no server to ask. Keeping the whole engine client-side means the file the user picks
 * never leaves their machine, and the page works identically on Vercel and on a static host.
 *
 * The layout follows the cost of each knob. Geometry — stop, target, hold — is free, because it
 * indexes a cached exit tensor, so those controls re-run on every keystroke. The rule costs an
 * indicator pass, so it re-runs on submit. That is the opposite of how a search is usually built
 * and it is what makes the loop feel immediate.
 *
 * Two things here exist because of what the numbers turned out to be, not because of taste. Every
 * column is a RESEARCH-block number: the table used to lead with whole-sample trade counts and
 * $/trade under a caption promising research-only figures, which is the holdout leaking into the
 * ranking. And the default ranking is residual Sharpe, because `CLAUDE.md` records that 87% of the
 * profit in the strategy this repository shipped was market beta that a raw Sharpe could not see.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CatalogueEntry } from "@/lib/quant/tuner/indicators";
import { RANK_KEYS, type RankKey } from "@/lib/quant/tuner";
import type { LoadedInfo, PublicReveal, PublicRow, PublicSweep } from "@/lib/quant/tuner/project";

const num = (s: string): number[] =>
  s
    .split(",")
    .map((x) => Number(x.trim()))
    .filter((x) => Number.isFinite(x));

/** The table is a ranking, not a report: showing more rows invites picking further down it. */
const ROW_CAP = 25;

const money = (v: number) => `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const one = (v: number) => (Number.isFinite(v) ? v.toFixed(1) : "—");
const two = (v: number) => (Number.isFinite(v) ? v.toFixed(2) : "—");
const pct = (v: number) => (Number.isFinite(v) ? `${(100 * v).toFixed(0)}%` : "—");
const mb = (v: number) => `${(v / (1024 * 1024)).toFixed(0)} MB`;

const RANK_LABEL: Record<RankKey, string> = {
  residSharpe: "residual Sharpe — Sharpe with the market regressed out",
  sharpe: "Sharpe — annualised, flat sessions included",
  perTrade: "$ per trade",
  netUsd: "net $",
  profitFactor: "profit factor",
  calmar: "Calmar — annual $ over max drawdown",
  tDaily: "t of mean session P&L",
};

/** A superseded sweep rejects with this; the UI drops it rather than showing it as an error. */
class Cancelled extends Error {}

/** Every request/response pair is promise-shaped so the component never juggles message ids. */
function useTunerWorker() {
  const ref = useRef<Worker | null>(null);
  const seq = useRef(0);
  const pending = useRef(new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void; onProgress?: (p: { done: number; total: number; phase: string }) => void }>());

  useEffect(() => {
    const w = new Worker(new URL("../lib/quant/tuner/worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (ev: MessageEvent) => {
      const { id, ok, payload, error, cancelled, progress } = ev.data ?? {};
      const p = pending.current.get(id);
      if (!p) return;
      if (progress) {
        p.onProgress?.(progress);
        return;
      }
      pending.current.delete(id);
      if (ok) p.resolve(payload);
      else p.reject(cancelled ? new Cancelled(error) : new Error(error ?? "worker failed"));
    };
    ref.current = w;
    return () => {
      w.terminate();
      // A terminated worker will never answer, so settle anything still waiting rather than
      // leaving promises — and the components awaiting them — alive for the page's lifetime.
      for (const p of pending.current.values()) p.reject(new Cancelled("worker closed"));
      pending.current.clear();
      ref.current = null;
    };
  }, []);

  return useCallback(<T,>(msg: Record<string, unknown>, onProgress?: (p: { done: number; total: number; phase: string }) => void): Promise<T> => {
    const w = ref.current;
    if (!w) return Promise.reject(new Error("worker not ready"));
    const id = ++seq.current;
    return new Promise<T>((resolve, reject) => {
      pending.current.set(id, { resolve: resolve as (v: unknown) => void, reject, onProgress });
      w.postMessage({ ...msg, id });
    });
  }, []);
}

function Panel({ title, hint, right, children }: { title: string; hint?: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-panel border border-white/[0.06] bg-white/[0.015] p-3 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-[10px] uppercase tracking-micro text-neutral-500">{title}</h2>
        {right}
      </div>
      {hint ? <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">{hint}</p> : null}
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

function Field({ label, value, onChange, placeholder, wide }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; wide?: boolean }) {
  return (
    <label className={`flex flex-col gap-1 ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-[10px] uppercase tracking-micro text-neutral-500">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 font-mono text-[12px] text-neutral-100 outline-none transition focus:border-accent/60"
      />
    </label>
  );
}

export function TunerConsole() {
  const call = useTunerWorker();
  const [info, setInfo] = useState<LoadedInfo | null>(null);
  const [cat, setCat] = useState<CatalogueEntry[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number; phase: string } | null>(null);

  const [symbol, setSymbol] = useState("MNQ");
  const [timeframe, setTimeframe] = useState(30);

  const [rule, setRule] = useState("close>ema200 and close<ema20");
  const [liveRule, setLiveRule] = useState("close>ema200 and close<ema20");
  const [params, setParams] = useState("");
  const [side, setSide] = useState<"long" | "short" | "both">("long");
  const [win, setWin] = useState("09:30-11:00");
  const [stops, setStops] = useState("1,1.5,2,2.5");
  const [targets, setTargets] = useState("0.5,1,1.5,2");
  const [holds, setHolds] = useState("12");
  const [atrPeriod, setAtrPeriod] = useState("14");
  const [costMults, setCostMults] = useState("1");
  const [minTrades, setMinTrades] = useState("30");
  const [rankBy, setRankBy] = useState<RankKey>("residSharpe");

  const [sweep, setSweep] = useState<PublicSweep | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [reveal, setReveal] = useState<PublicReveal[] | null>(null);

  useEffect(() => {
    call<CatalogueEntry[]>({ kind: "catalogue" }).then(setCat).catch(() => undefined);
  }, [call]);

  const loadDemo = useCallback(async () => {
    setBusy("generating synthetic bars");
    setError(null);
    try {
      const i = await call<LoadedInfo>({ kind: "load", source: { type: "demo", days: 400 }, symbol, timeframe });
      setInfo(i);
      setSweep(null);
      setReveal(null);
    } catch (e) {
      if (!(e instanceof Cancelled)) setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, [call, symbol, timeframe]);

  const loadFile = useCallback(
    async (file: File) => {
      setBusy(`reading ${file.name}`);
      setError(null);
      try {
        // The File goes across as a handle; the worker reads it. Calling `file.text()` here would
        // block the page on a hundred-megabyte decode and then clone the whole string anyway.
        const i = await call<LoadedInfo>({ kind: "load", source: { type: "csv", file }, symbol, timeframe });
        setInfo(i);
        setSweep(null);
        setReveal(null);
      } catch (e) {
        if (!(e instanceof Cancelled)) setError((e as Error).message);
      } finally {
        setBusy(null);
      }
    },
    [call, symbol, timeframe],
  );

  const axes = useMemo(() => {
    const p: Record<string, number[]> = {};
    for (const part of params.split(";")) {
      const [k, v] = part.split("=");
      if (k?.trim() && v) p[k.trim()] = num(v);
    }
    return {
      rule: liveRule,
      sides: side === "both" ? ([1, -1] as (1 | -1)[]) : side === "long" ? ([1] as (1 | -1)[]) : ([-1] as (1 | -1)[]),
      windows: win.split(",").map((x) => x.trim()).filter(Boolean),
      stops: num(stops),
      targets: num(targets),
      maxBars: num(holds),
      atrPeriod: num(atrPeriod)[0] ?? 14,
      costs: num(costMults).map((m) => ({ fillModel: "taker" as const, mult: m })),
      params: p,
      minTrades: num(minTrades)[0] ?? 30,
      rankBy,
    };
  }, [liveRule, side, win, stops, targets, holds, atrPeriod, costMults, minTrades, params, rankBy]);

  /** What this grid will cost, computed before anything is built rather than discovered by a hang. */
  const preflight = useMemo(() => {
    let combos = 1;
    for (const vals of Object.values(axes.params)) combos *= Math.max(vals.length, 1);
    const geoms = axes.stops.length * axes.targets.length * axes.maxBars.length;
    const total = axes.sides.length * axes.windows.length * combos * axes.costs.length * geoms;
    const perTensor = info?.geometriesPerTensor ?? 0;
    const tensors = perTensor ? Math.ceil(geoms / perTensor) : 0;
    const bytes = info ? Math.min(geoms, perTensor || geoms) * info.bars * 13 : 0;
    return { total, geoms, tensors, bytes };
  }, [axes, info]);

  // Geometry knobs are free, so they re-run on change. The rule is not, so it waits for submit.
  useEffect(() => {
    if (!info) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setBusy("sweeping");
      setError(null);
      setReveal(null);
      call<PublicSweep>({ kind: "sweep", axes }, (p) => !cancelled && setProgress(p))
        .then((r) => {
          if (cancelled) return;
          setSweep(r);
          setPicked([]);
        })
        .catch((e) => {
          // A superseded sweep is the normal case while someone is typing, not a failure.
          if (!cancelled && !(e instanceof Cancelled)) setError((e as Error).message);
        })
        .finally(() => {
          if (!cancelled) {
            setBusy(null);
            setProgress(null);
          }
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [axes, info, call]);

  const stop = useCallback(() => {
    void call({ kind: "cancel" }).catch(() => undefined);
    setBusy(null);
    setProgress(null);
  }, [call]);

  const doReveal = useCallback(async () => {
    if (!picked.length) return;
    setBusy("reading the locked block");
    try {
      const r = await call<PublicReveal[]>({ kind: "reveal", keys: picked, draws: 4000 });
      setReveal(r);
    } catch (e) {
      if (!(e instanceof Cancelled)) setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, [call, picked]);

  const varying = useMemo(() => {
    const rows = sweep?.rows ?? [];
    const distinct = (f: (r: PublicRow) => unknown) => new Set(rows.map(f)).size > 1;
    return {
      stop: distinct((r) => r.stop),
      target: distinct((r) => r.target),
      maxBars: distinct((r) => r.maxBars),
      window: distinct((r) => r.window),
      side: distinct((r) => r.side),
      cost: distinct((r) => r.costLabel),
      rule: distinct((r) => r.rule),
    };
  }, [sweep]);

  const paramKeys = useMemo(() => Array.from(new Set((sweep?.rows ?? []).flatMap((r) => Object.keys(r.params)))), [sweep]);

  return (
    <div className="space-y-3 font-mono">
      {/* ---------------- data ---------------- */}
      <Panel
        title="Bars"
        hint="Files stay on your machine — the engine runs in this tab, so nothing is uploaded. Bar data is git-ignored for exactly that reason."
      >
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Instrument" value={symbol} onChange={setSymbol} placeholder="MNQ" />
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-micro text-neutral-500">Timeframe</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(Number(e.target.value))}
              className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[12px] text-neutral-100 outline-none focus:border-accent/60"
            >
              {[1, 5, 15, 30, 60].map((m) => (
                <option key={m} value={m}>
                  {m} minute
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-micro text-neutral-500">CSV</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void loadFile(f);
              }}
              className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[11px] text-neutral-400 file:mr-2 file:rounded file:border-0 file:bg-white/10 file:px-2 file:py-1 file:text-[11px] file:text-neutral-200"
            />
          </label>
          <button
            type="button"
            onClick={() => void loadDemo()}
            className="min-h-9 self-end rounded border border-white/10 bg-white/[0.04] px-3 text-[11px] uppercase tracking-micro text-neutral-300 transition hover:border-white/20 hover:text-accent-bright"
          >
            Synthetic demo
          </button>
        </div>

        {info ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-white/5 pt-2.5 text-[11px] text-neutral-400">
            <span className="text-neutral-200">
              {info.bars.toLocaleString()} bars · {info.sessions.toLocaleString()} sessions · {info.timeframe}m
            </span>
            <span>
              {new Date(info.firstMs).toISOString().slice(0, 10)} → {new Date(info.lastMs).toISOString().slice(0, 10)}
            </span>
            <span>
              research {info.researchSessions.toLocaleString()} / locked {info.lockedSessions.toLocaleString()} sessions
            </span>
            <span className="text-neutral-500">{info.geometriesPerTensor.toLocaleString()} geometries per tensor</span>
            {info.synthetic ? (
              <span className="rounded border border-put/40 bg-put/10 px-1.5 py-0.5 text-put">
                SYNTHETIC — no edge exists in these bars by construction
              </span>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 border-t border-white/5 pt-2.5 text-[11px] text-neutral-500">
            Load <code className="text-neutral-300">timestamp,open,high,low,close,volume</code> in UTC ISO-8601, or press{" "}
            <span className="text-neutral-300">Synthetic demo</span> to try the controls against bars with no edge in them.
          </p>
        )}
      </Panel>

      {/* ---------------- rule ---------------- */}
      <Panel title="Entry rule" hint="Any indicator at any period — ema200, rsi14, stretch10 — or call form: macd(12,26,9), cross(9,21). Use {n} for a swept period.">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setLiveRule(rule);
          }}
          className="grid gap-2.5 sm:grid-cols-3"
        >
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[10px] uppercase tracking-micro text-neutral-500">Rule</span>
            <input
              value={rule}
              onChange={(e) => setRule(e.target.value)}
              spellCheck={false}
              className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 font-mono text-[12px] text-neutral-100 outline-none transition focus:border-accent/60"
            />
          </label>
          <Field label="Sweep {name}=values" value={params} onChange={setParams} placeholder="n=50,100,200; p=7,14" />
          <div className="sm:col-span-3 flex flex-wrap items-center gap-2">
            <button
              type="submit"
              className="min-h-9 rounded border border-accent/40 bg-accent/10 px-3 text-[11px] uppercase tracking-micro text-accent-bright transition hover:bg-accent/20"
            >
              Apply rule
            </button>
            {rule !== liveRule ? <span className="text-[11px] text-neutral-500">unapplied edit — the rule costs an indicator pass, the knobs below do not</span> : null}
          </div>
        </form>
      </Panel>

      {/* ---------------- knobs ---------------- */}
      <Panel title="Session, entry and exits" hint="These index a cached exit tensor, so they re-run as you type.">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-micro text-neutral-500">Side</span>
            <select
              value={side}
              onChange={(e) => setSide(e.target.value as "long" | "short" | "both")}
              className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[12px] text-neutral-100 outline-none focus:border-accent/60"
            >
              <option value="long">long</option>
              <option value="short">short</option>
              <option value="both">both</option>
            </select>
          </label>
          <Field label="Window (NY)" value={win} onChange={setWin} placeholder="09:30-11:00" />
          <Field label="Stop × ATR" value={stops} onChange={setStops} />
          <Field label="Target × R" value={targets} onChange={setTargets} />
          <Field label="Max hold (bars)" value={holds} onChange={setHolds} />
          <Field label="ATR period" value={atrPeriod} onChange={setAtrPeriod} />
          <Field label="Cost ×" value={costMults} onChange={setCostMults} placeholder="1,2" />
          <Field label="Min trades" value={minTrades} onChange={setMinTrades} />
          <label className="flex flex-col gap-1 sm:col-span-2 lg:col-span-4">
            <span className="text-[10px] uppercase tracking-micro text-neutral-500">Rank by (research block)</span>
            <select
              value={rankBy}
              onChange={(e) => setRankBy(e.target.value as RankKey)}
              className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[12px] text-neutral-100 outline-none focus:border-accent/60"
            >
              {RANK_KEYS.map((k) => (
                <option key={k} value={k}>
                  {RANK_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
        </div>

        {info ? (
          <p className="mt-2.5 border-t border-white/5 pt-2.5 text-[11px] leading-relaxed text-neutral-500">
            {preflight.total.toLocaleString()} configurations · {preflight.geoms.toLocaleString()} geometries in{" "}
            {preflight.tensors.toLocaleString()} tensor{preflight.tensors === 1 ? "" : "s"} · about {mb(preflight.bytes)} of exit tensor held at a time.
          </p>
        ) : null}
      </Panel>

      {error ? (
        <p role="alert" className="rounded-panel border border-put/40 bg-put/10 px-3 py-2 text-[12px] text-put">
          {error}
        </p>
      ) : null}

      {/* ---------------- results ---------------- */}
      {sweep ? (
        <Panel
          title="Research block"
          right={
            busy ? (
              <button
                type="button"
                onClick={stop}
                className="min-h-7 rounded border border-put/40 bg-put/10 px-2 text-[10px] uppercase tracking-micro text-put transition hover:bg-put/20"
              >
                Stop
              </button>
            ) : undefined
          }
        >
          <p className="text-[11px] leading-relaxed text-neutral-400">
            <span className="text-neutral-200">{sweep.evaluated.toLocaleString()}</span> configurations in{" "}
            <span className="text-neutral-200">{(sweep.ms / 1000).toFixed(2)}s</span> ({(sweep.tensorMs / 1000).toFixed(2)}s building{" "}
            {sweep.tensors} exit tensor{sweep.tensors === 1 ? "" : "s"},{" "}
            {((sweep.ms - sweep.tensorMs) / Math.max(sweep.evaluated, 1)).toFixed(2)} ms each after that)
            {sweep.dropped ? ` · ${sweep.dropped.toLocaleString()} dropped for fewer than ${sweep.minTrades} trades` : ""}. Ranked on{" "}
            <span className="text-neutral-300">{RANK_LABEL[sweep.rankBy]}</span>.
            {sweep.rows.length > ROW_CAP ? ` Showing the top ${ROW_CAP} of ${sweep.rows.length.toLocaleString()}.` : ""}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">
            <span className="text-neutral-300">{(sweep.evaluated * 0.05).toFixed(1)}</span> of them are expected to reach p&lt;0.05 by chance. Every column
            below is a research-block number — the last 35% of sessions is not computed into anything you can see until you choose rows and read it once.
          </p>

          {sweep.rows.length === 0 ? (
            <p className="mt-2.5 rounded border border-white/10 bg-black/30 px-3 py-2.5 text-[11px] leading-relaxed text-neutral-400">
              Nothing kept {sweep.minTrades} trades or more. A rule this selective cannot be told apart from noise at any threshold, so the honest move is to
              loosen it or lower the floor deliberately — not to read whichever cell survived.
            </p>
          ) : (
          <div className="mt-2.5 overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse text-[11px] tabular-nums">
              <thead>
                <tr className="border-b border-white/10 text-left text-[10px] uppercase tracking-micro text-neutral-500">
                  <th className="py-1.5 pr-2 font-normal"> </th>
                  {varying.rule && !paramKeys.length ? <th className="py-1.5 pr-3 font-normal">rule</th> : null}
                  {paramKeys.map((k) => (
                    <th key={k} className="py-1.5 pr-3 font-normal text-accent-bright">
                      {`{${k}}`}
                    </th>
                  ))}
                  {varying.side ? <th className="py-1.5 pr-3 font-normal">side</th> : null}
                  {varying.window ? <th className="py-1.5 pr-3 font-normal">window</th> : null}
                  {varying.stop ? <th className="py-1.5 pr-3 font-normal">stop</th> : null}
                  {varying.target ? <th className="py-1.5 pr-3 font-normal">target</th> : null}
                  {varying.maxBars ? <th className="py-1.5 pr-3 font-normal">hold</th> : null}
                  {varying.cost ? <th className="py-1.5 pr-3 font-normal">cost</th> : null}
                  <th className="py-1.5 pr-3 text-right font-normal">trades</th>
                  <th className="py-1.5 pr-3 text-right font-normal">$/trade</th>
                  <th className="py-1.5 pr-3 text-right font-normal">win %</th>
                  <th className="py-1.5 pr-3 text-right font-normal">PF</th>
                  <th className="py-1.5 pr-3 text-right font-normal">sharpe</th>
                  <th className="py-1.5 pr-3 text-right font-normal" title="Sharpe with the market's own move across the window regressed out">
                    resid
                  </th>
                  <th className="py-1.5 pr-3 text-right font-normal" title="Share of P&L the market exposure explains">
                    β share
                  </th>
                  <th className="py-1.5 pr-3 text-right font-normal" title="Largest share of P&L in any one fifth of the block">
                    conc
                  </th>
                  <th className="py-1.5 pr-3 text-right font-normal">max DD</th>
                </tr>
              </thead>
              <tbody>
                {sweep.rows.slice(0, ROW_CAP).map((r) => {
                  const on = picked.includes(r.key);
                  const p = r.research;
                  return (
                    <tr key={r.key} className={`border-b border-white/5 ${on ? "bg-accent/[0.07]" : ""}`}>
                      <td className="py-1 pr-2">
                        <input
                          type="checkbox"
                          checked={on}
                          aria-label={`select ${r.rule} ${r.stop}x${r.target}R`}
                          onChange={() => setPicked((q) => (q.includes(r.key) ? q.filter((x) => x !== r.key) : [...q, r.key]))}
                          className="h-3.5 w-3.5 accent-emerald-400"
                        />
                      </td>
                      {varying.rule && !paramKeys.length ? <td className="py-1 pr-3 text-neutral-300">{r.rule}</td> : null}
                      {paramKeys.map((k) => (
                        <td key={k} className="py-1 pr-3 text-neutral-300">
                          {r.params[k]}
                        </td>
                      ))}
                      {varying.side ? <td className="py-1 pr-3 text-neutral-400">{r.side === 1 ? "long" : "short"}</td> : null}
                      {varying.window ? <td className="py-1 pr-3 text-neutral-400">{r.window}</td> : null}
                      {varying.stop ? <td className="py-1 pr-3 text-neutral-400">{r.stop}</td> : null}
                      {varying.target ? <td className="py-1 pr-3 text-neutral-400">{r.target}</td> : null}
                      {varying.maxBars ? <td className="py-1 pr-3 text-neutral-400">{r.maxBars}</td> : null}
                      {varying.cost ? <td className="py-1 pr-3 text-neutral-400">{r.costLabel}</td> : null}
                      <td className="py-1 pr-3 text-right text-neutral-300">{p.trades}</td>
                      <td className={`py-1 pr-3 text-right ${p.perTrade > 0 ? "text-call" : "text-put"}`}>{one(p.perTrade)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{one(p.winPct)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{two(p.profitFactor)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{two(p.sharpe)}</td>
                      <td className={`py-1 pr-3 text-right ${p.residSharpe > 0 ? "text-call" : "text-put"}`}>{two(p.residSharpe)}</td>
                      <td className={`py-1 pr-3 text-right ${Number.isFinite(p.betaPnlShare) && p.betaPnlShare > 0.5 ? "text-put" : "text-neutral-400"}`}>
                        {pct(p.betaPnlShare)}
                      </td>
                      <td className={`py-1 pr-3 text-right ${Number.isFinite(p.concentration) && p.concentration > 0.6 ? "text-put" : "text-neutral-400"}`}>
                        {pct(p.concentration)}
                      </td>
                      <td className="py-1 pr-3 text-right text-neutral-500">{money(p.maxDrawdown)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}

          {sweep.rows.length ? (
          <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-white/5 pt-2.5">
            <button
              type="button"
              disabled={!picked.length}
              onClick={() => void doReveal()}
              className="min-h-9 rounded border border-white/15 bg-white/[0.04] px-3 text-[11px] uppercase tracking-micro text-neutral-300 transition enabled:hover:border-put/50 enabled:hover:text-put disabled:opacity-40"
            >
              Read the locked block ({picked.length})
            </button>
            <span className="text-[11px] text-neutral-500">
              Reading it is a one-way door: once the holdout has informed a choice, it is part of the selection.
            </span>
          </div>
          ) : null}
        </Panel>
      ) : null}

      {reveal ? (
        <Panel title="Locked block — read once" hint={`${reveal[0]?.searched.toLocaleString() ?? 0} configurations were searched, so the Bonferroni threshold for one claim is p < ${reveal[0]?.bonferroni.toExponential(1) ?? "—"}`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[11px] tabular-nums">
              <thead>
                <tr className="border-b border-white/10 text-left text-[10px] uppercase tracking-micro text-neutral-500">
                  <th className="py-1.5 pr-3 font-normal">rule</th>
                  <th className="py-1.5 pr-3 text-right font-normal">stop/target</th>
                  <th className="py-1.5 pr-3 text-right font-normal">res $/tr</th>
                  <th className="py-1.5 pr-3 text-right font-normal">lok trades</th>
                  <th className="py-1.5 pr-3 text-right font-normal">lok $/tr</th>
                  <th className="py-1.5 pr-3 text-right font-normal">lok net</th>
                  <th className="py-1.5 pr-3 text-right font-normal">lok resid</th>
                  <th className="py-1.5 pr-3 text-right font-normal">control</th>
                  <th className="py-1.5 pr-3 text-right font-normal">p</th>
                  <th className="py-1.5 pr-3 font-normal">shape</th>
                </tr>
              </thead>
              <tbody>
                {reveal.map((r) => (
                  <tr key={r.row.key} className="border-b border-white/5">
                    <td className="py-1 pr-3 text-neutral-300">{r.row.rule}</td>
                    <td className="py-1 pr-3 text-right text-neutral-400">
                      {r.row.stop}×/{r.row.target}R
                    </td>
                    <td className="py-1 pr-3 text-right text-neutral-400">{one(r.row.research.perTrade)}</td>
                    <td className="py-1 pr-3 text-right text-neutral-400">{r.locked.trades}</td>
                    <td className={`py-1 pr-3 text-right ${r.locked.perTrade > 0 ? "text-call" : "text-put"}`}>{one(r.locked.perTrade)}</td>
                    <td className="py-1 pr-3 text-right text-neutral-400">{money(r.locked.netUsd)}</td>
                    <td className={`py-1 pr-3 text-right ${r.locked.residSharpe > 0 ? "text-call" : "text-put"}`}>{two(r.locked.residSharpe)}</td>
                    <td className="py-1 pr-3 text-right text-neutral-500">{one(r.control.meanLocked)}</td>
                    <td className={`py-1 pr-3 text-right ${r.control.pLocked < 0.05 ? "text-call" : "text-neutral-400"}`}>{r.control.pLocked.toFixed(3)}</td>
                    <td className={`py-1 pr-3 ${r.shape === "decays" ? "text-neutral-500" : "text-put"}`}>
                      {r.shape === "decays" ? "decays" : "GREW ON LOCKED — wrong shape"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">
            The shape to want is a research number that <span className="text-neutral-300">decays</span>. A configuration that is better on the holdout than on
            research is the wrong shape — the holdout is where an edge decays, not where it appears — and has twice been a defect in this project rather than a
            result. Read <span className="text-neutral-300">lok resid</span> next to <span className="text-neutral-300">lok $/tr</span>: a holdout that made
            money with no residual made it by being in the market.
          </p>
        </Panel>
      ) : null}

      {/* ---------------- reference ---------------- */}
      {cat.length ? (
        <details className="rounded-panel border border-white/[0.06] bg-white/[0.015] p-3">
          <summary className="cursor-pointer text-[10px] uppercase tracking-micro text-neutral-500">Indicators ({cat.length})</summary>
          <div className="mt-2.5 grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
            {cat.map((c) => (
              <div key={c.name} className="flex gap-2 text-[11px]">
                <code className="shrink-0 text-accent-bright">
                  {c.name}
                  {c.arity === 1 ? "N" : c.arity > 1 ? `(${Array.from({ length: c.arity }, (_, i) => String.fromCharCode(97 + i)).join(",")})` : ""}
                </code>
                <span className="text-neutral-500">{c.doc}</span>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {busy ? (
        <p aria-live="polite" className="text-[11px] text-neutral-500">
          {busy}
          {progress
            ? progress.phase === "tensor"
              ? ` — building exit tensor, geometry ${progress.done} of ${progress.total}`
              : ` ${Math.round((100 * progress.done) / Math.max(progress.total, 1))}%`
            : "…"}
        </p>
      ) : null}
    </div>
  );
}
