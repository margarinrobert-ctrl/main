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
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CatalogueEntry } from "@/lib/quant/tuner/indicators";
import type { LoadedInfo } from "@/lib/quant/tuner/worker";

type SweepRowLite = {
  key: string;
  rule: string;
  params: Record<string, number>;
  side: 1 | -1;
  window: string;
  stop: number;
  target: number;
  maxBars: number;
  costLabel: string;
  n: number;
  perTrade: number;
  netUsd: number;
  winPct: number;
  profitFactor: number;
  maxDrawdown: number;
  tStat: number;
  stopPct: number;
  nResearch: number;
  perTradeResearch: number;
  winPctResearch: number;
};

type SweepLite = { rows: SweepRowLite[]; evaluated: number; dropped: number; minTrades: number; ms: number; tensorMs: number };
type EdgeLite = {
  winPct: number;
  baseRatePct: number | null;
  excessWinPct: number | null;
  perTrade: number;
  controlPerTrade: number | null;
  excessPerTrade: number | null;
  timeStopShare: number;
  searched: number;
  bonferroni: number;
  warnings: string[];
};

type RevealLite = {
  hurdle: { ticks: number; usd: number; worstTicks: number; shareOfBar: number | null };
  exits: { reason: string; n: number; share: number }[];
  edge: EdgeLite;
  row: SweepRowLite;
  window: string;
  locked: { n: number; perTrade: number; netUsd: number; winPct: number };
  control: { draws: number; meanLocked: number; pLocked: number; meanResearch: number; pResearch: number };
  shape: "decays" | "grew-on-locked";
  searched: number;
  bonferroni: number;
};

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

/** Every request/response pair is promise-shaped so the component never juggles message ids. */
function useTunerWorker() {
  const ref = useRef<Worker | null>(null);
  const seq = useRef(0);
  const pending = useRef(new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void; onProgress?: (d: number, t: number) => void }>());

  useEffect(() => {
    const w = new Worker(new URL("../lib/quant/tuner/worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (ev: MessageEvent) => {
      const { id, ok, payload, error, progress } = ev.data ?? {};
      const p = pending.current.get(id);
      if (!p) return;
      if (progress) {
        p.onProgress?.(progress.done, progress.total);
        return;
      }
      pending.current.delete(id);
      if (ok) p.resolve(payload);
      else p.reject(new Error(error ?? "worker failed"));
    };
    ref.current = w;
    return () => {
      w.terminate();
      ref.current = null;
    };
  }, []);

  return useCallback(<T,>(msg: Record<string, unknown>, onProgress?: (d: number, t: number) => void): Promise<T> => {
    const w = ref.current;
    if (!w) return Promise.reject(new Error("worker not ready"));
    const id = ++seq.current;
    return new Promise<T>((resolve, reject) => {
      pending.current.set(id, { resolve: resolve as (v: unknown) => void, reject, onProgress });
      w.postMessage({ ...msg, id });
    });
  }, []);
}

function Panel({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-panel border border-white/[0.06] bg-white/[0.015] p-3 shadow-panel">
      <h2 className="text-[10px] uppercase tracking-micro text-neutral-500">{title}</h2>
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
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const [symbol, setSymbol] = useState("MNQ");
  const [timeframe, setTimeframe] = useState(30);
  const [broker, setBroker] = useState("discount");

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

  const [sweep, setSweep] = useState<SweepLite | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [reveal, setReveal] = useState<RevealLite[] | null>(null);

  useEffect(() => {
    call<CatalogueEntry[]>({ kind: "catalogue" }).then(setCat).catch(() => undefined);
  }, [call]);

  const loadDemo = useCallback(async () => {
    setBusy("generating synthetic bars");
    setError(null);
    try {
      const i = await call<LoadedInfo>({ kind: "load", source: { type: "demo", days: 400 }, symbol, timeframe, broker });
      setInfo(i);
      setSweep(null);
      setReveal(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, [call, symbol, timeframe, broker]);

  const loadFile = useCallback(
    async (file: File) => {
      setBusy(`reading ${file.name}`);
      setError(null);
      try {
        const text = await file.text();
        const i = await call<LoadedInfo>({ kind: "load", source: { type: "csv", text }, symbol, timeframe, broker });
        setInfo(i);
        setSweep(null);
        setReveal(null);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(null);
      }
    },
    [call, symbol, timeframe, broker],
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
    };
  }, [liveRule, side, win, stops, targets, holds, atrPeriod, costMults, minTrades, params]);

  // Geometry knobs are free, so they re-run on change. The rule is not, so it waits for submit.
  useEffect(() => {
    if (!info) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setBusy("sweeping");
      setError(null);
      setReveal(null);
      call<SweepLite>({ kind: "sweep", axes }, (done, total) => setProgress({ done, total }))
        .then((r) => {
          if (cancelled) return;
          setSweep(r);
          setPicked([]);
        })
        .catch((e) => !cancelled && setError((e as Error).message))
        .finally(() => {
          if (!cancelled) {
            setBusy(null);
            setProgress(null);
          }
        });
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [axes, info, call]);

  const doReveal = useCallback(async () => {
    if (!picked.length) return;
    setBusy("reading the locked block");
    try {
      const r = await call<RevealLite[]>({ kind: "reveal", keys: picked, draws: 4000 });
      setReveal(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, [call, picked]);

  const varying = useMemo(() => {
    const rows = sweep?.rows ?? [];
    const distinct = (f: (r: SweepRowLite) => unknown) => new Set(rows.map(f)).size > 1;
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
            <span className="text-[10px] uppercase tracking-micro text-neutral-500">Broker</span>
            <select
              value={broker}
              onChange={(e) => setBroker(e.target.value)}
              className="min-h-9 rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[12px] text-neutral-100 outline-none focus:border-accent/60"
            >
              {["discount", "ibkr", "propfirm", "premium"].map((b) => (
                <option key={b} value={b}>
                  {b}
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
            <span className="text-neutral-300">round turn {info.roundTurnTicks.toFixed(2)} ticks</span>
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
        {info ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-[10px] uppercase tracking-micro text-neutral-500">
              What a round turn costs
            </summary>
            <pre className="mt-1.5 overflow-x-auto whitespace-pre rounded border border-white/10 bg-black/40 p-2.5 text-[11px] leading-relaxed text-neutral-400">
{info.costs}
            </pre>
            <p className="mt-1.5 text-[11px] leading-relaxed text-neutral-500">
              Fee values are dated assumptions, not quotes. Slippage is a model, not a measurement — bars are not order books. Replace both with your own
              statement before sizing real risk.
            </p>
          </details>
        ) : null}
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
        </div>
      </Panel>

      {error ? (
        <p role="alert" className="rounded-panel border border-put/40 bg-put/10 px-3 py-2 text-[12px] text-put">
          {error}
        </p>
      ) : null}

      {/* ---------------- results ---------------- */}
      {sweep ? (
        <Panel title="Research block">
          <p className="text-[11px] leading-relaxed text-neutral-400">
            <span className="text-neutral-200">{sweep.evaluated.toLocaleString()}</span> configurations in{" "}
            <span className="text-neutral-200">{(sweep.ms / 1000).toFixed(2)}s</span> ({(sweep.tensorMs / 1000).toFixed(2)}s building the exit tensor,{" "}
            {((sweep.ms - sweep.tensorMs) / Math.max(sweep.evaluated, 1)).toFixed(2)} ms each after that)
            {sweep.dropped ? ` · ${sweep.dropped.toLocaleString()} dropped for fewer than ${sweep.minTrades} trades` : ""}.
            {sweep.rows.length > ROW_CAP ? ` Showing the top ${ROW_CAP} of ${sweep.rows.length.toLocaleString()} by research $/trade.` : ""}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-neutral-500">
            <span className="text-neutral-300">{(sweep.evaluated * 0.05).toFixed(1)}</span> of them are expected to reach p&lt;0.05 by chance. These are
            research-block numbers only — the last 35% of sessions is not shown until you choose rows and read it once.
          </p>

          {sweep.rows.length === 0 ? (
            <p className="mt-2.5 rounded border border-white/10 bg-black/30 px-3 py-2.5 text-[11px] leading-relaxed text-neutral-400">
              Nothing kept {sweep.minTrades} trades or more. A rule this selective cannot be told apart from noise at any threshold, so the honest move is to
              loosen it or lower the floor deliberately — not to read whichever cell survived.
            </p>
          ) : (
          <div className="mt-2.5 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-[11px] tabular-nums">
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
                  <th className="py-1.5 pr-3 text-right font-normal">res trades</th>
                  <th className="py-1.5 pr-3 text-right font-normal">res $/tr</th>
                  <th className="py-1.5 pr-3 text-right font-normal">res win %</th>
                </tr>
              </thead>
              <tbody>
                {sweep.rows.slice(0, ROW_CAP).map((r) => {
                  const on = picked.includes(r.key);
                  return (
                    <tr key={r.key} className={`border-b border-white/5 ${on ? "bg-accent/[0.07]" : ""}`}>
                      <td className="py-1 pr-2">
                        <input
                          type="checkbox"
                          checked={on}
                          aria-label={`select ${r.rule} ${r.stop}x${r.target}R`}
                          onChange={() => setPicked((p) => (p.includes(r.key) ? p.filter((x) => x !== r.key) : [...p, r.key]))}
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
                      <td className="py-1 pr-3 text-right text-neutral-300">{r.n}</td>
                      <td className={`py-1 pr-3 text-right ${r.perTrade > 0 ? "text-call" : "text-put"}`}>{one(r.perTrade)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{one(r.winPct)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{two(r.profitFactor)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{r.nResearch}</td>
                      <td className={`py-1 pr-3 text-right ${r.perTradeResearch > 0 ? "text-call" : "text-put"}`}>{one(r.perTradeResearch)}</td>
                      <td className="py-1 pr-3 text-right text-neutral-400">{one(r.winPctResearch)}</td>
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
                    <td className="py-1 pr-3 text-right text-neutral-400">{one(r.row.perTradeResearch)}</td>
                    <td className="py-1 pr-3 text-right text-neutral-400">{r.locked.n}</td>
                    <td className={`py-1 pr-3 text-right ${r.locked.perTrade > 0 ? "text-call" : "text-put"}`}>{one(r.locked.perTrade)}</td>
                    <td className="py-1 pr-3 text-right text-neutral-400">{money(r.locked.netUsd)}</td>
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
          {/* ---- edge diagnostics: the questions that decide whether this is an edge at all ---- */}
          {reveal.map((r) => (
            <div key={`edge-${r.row.key}`} className="mt-3 rounded-lg border border-white/[0.08] bg-black/30 p-3">
              <h3 className="text-[10px] uppercase tracking-micro text-neutral-500">
                Edge report · {r.row.rule} · {r.row.stop}×/{r.row.target}R
              </h3>

              <div className="mt-2 grid gap-3 sm:grid-cols-3">
                <div>
                  <div className="text-[10px] uppercase tracking-micro text-neutral-500">Cost hurdle</div>
                  <div className="mt-0.5 text-[12px] text-neutral-200">
                    {r.hurdle.ticks.toFixed(2)} ticks <span className="text-neutral-500">= ${r.hurdle.usd.toFixed(2)}</span>
                  </div>
                  <div className="text-[11px] text-neutral-500">
                    {r.hurdle.shareOfBar !== null ? `${(100 * r.hurdle.shareOfBar).toFixed(0)}% of a median bar` : "median bar unknown"} ·
                    worst {r.hurdle.worstTicks.toFixed(1)}t
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-micro text-neutral-500">Win rate vs its base rate</div>
                  <div className="mt-0.5 text-[12px] text-neutral-200">
                    {r.edge.winPct.toFixed(1)}%
                    {r.edge.baseRatePct !== null ? <span className="text-neutral-500"> vs {r.edge.baseRatePct.toFixed(1)}% base</span> : null}
                  </div>
                  <div className={`text-[11px] ${(r.edge.excessWinPct ?? 0) > 0 ? "text-call" : "text-put"}`}>
                    {r.edge.excessWinPct === null ? "no control" : `${r.edge.excessWinPct >= 0 ? "+" : ""}${r.edge.excessWinPct.toFixed(1)} pts excess`}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-micro text-neutral-500">Where the exits landed</div>
                  <div className="mt-0.5 flex h-2 overflow-hidden rounded-full bg-white/5">
                    {r.exits.map((e) => (
                      <span
                        key={e.reason}
                        title={`${e.reason} ${e.n} (${Math.round(100 * e.share)}%)`}
                        style={{ width: `${100 * e.share}%` }}
                        className={
                          e.reason === "target" ? "bg-call/70" : e.reason === "stop" ? "bg-put/70" : "bg-amber-400/60"
                        }
                      />
                    ))}
                  </div>
                  <div className="mt-1 text-[11px] text-neutral-500">
                    {r.exits.filter((e) => e.n > 0).map((e) => `${e.reason} ${Math.round(100 * e.share)}%`).join(" · ")}
                  </div>
                </div>
              </div>

              {r.edge.warnings.length ? (
                <ul className="mt-2.5 space-y-1 border-t border-white/5 pt-2">
                  {r.edge.warnings.map((w) => (
                    <li key={w} className="flex gap-2 text-[11px] leading-relaxed text-amber-200/90">
                      <span aria-hidden className="text-amber-400">
                        ▸
                      </span>
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2.5 border-t border-white/5 pt-2 text-[11px] leading-relaxed text-neutral-400">
                  No diagnostic fired. That means nothing objectionable was found — not that this is an edge.
                </p>
              )}
            </div>
          ))}

          <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">
            The shape to want is a research number that <span className="text-neutral-300">decays</span>. A configuration that is better on the holdout than on
            research is the wrong shape — the holdout is where an edge decays, not where it appears — and has twice been a defect in this project rather than a
            result.
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
          {progress ? ` ${Math.round((100 * progress.done) / Math.max(progress.total, 1))}%` : "…"}
        </p>
      ) : null}
    </div>
  );
}
