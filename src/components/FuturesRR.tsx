"use client";

import { useMemo, useState } from "react";
import { computeTradeRR, FUTURES, pointValue, type RRResult, type Side } from "@/lib/quant/futuresrr";
import { Stat } from "./states";

// ── formatting ────────────────────────────────────────────────────────────────────────────────
const money = (v: number): string => {
  const a = Math.abs(v);
  const s = v < 0 ? "−" : "";
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${s}$${(a / 1e3).toFixed(1)}K`;
  return `${s}$${a.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};
const pct = (p: number | null, d = 1): string => (p == null ? "—" : `${(p * 100).toFixed(d)}%`);
const num = (v: number, d = 2): string => v.toLocaleString(undefined, { maximumFractionDigits: d });

// ── small controlled inputs ─────────────────────────────────────────────────────────────────
function Field({
  label,
  value,
  onChange,
  placeholder,
  suffix,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  suffix?: string;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="lbl">{label}</span>
      <div className="relative mt-1">
        <input
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 font-mono text-sm tabular-nums text-neutral-100 outline-none transition placeholder:text-neutral-600 hover:border-white/20 focus:border-accent/50"
        />
        {suffix && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-neutral-500">{suffix}</span>}
      </div>
      {hint && <span className="mt-1 block text-[11px] leading-snug text-neutral-500">{hint}</span>}
    </label>
  );
}

const parse = (s: string): number => {
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : Number.NaN;
};

export function FuturesRR() {
  const [side, setSide] = useState<Side>("long");
  const [sym, setSym] = useState("ES");
  const [tickSize, setTickSize] = useState("0.25");
  const [tickValue, setTickValue] = useState("12.5");
  const [entry, setEntry] = useState("5000");
  const [stop, setStop] = useState("4990");
  const [target, setTarget] = useState("5020");
  const [contracts, setContracts] = useState("1");
  const [showEdge, setShowEdge] = useState(false);
  const [commission, setCommission] = useState("");
  const [slippage, setSlippage] = useState("");
  const [atr, setAtr] = useState("");
  const [bars, setBars] = useState("");
  const [drift, setDrift] = useState("");
  const [winRate, setWinRate] = useState("");

  const spec = useMemo(() => FUTURES.find((f) => f.symbol === sym) ?? null, [sym]);
  const ts = spec ? spec.tickSize : parse(tickSize);
  const tv = spec ? spec.tickValue : parse(tickValue);

  // Horizon 1σ from ATR × √bars (a familiar way to express expected range over a holding window).
  const horizonSigma = useMemo(() => {
    const a = parse(atr);
    const n = parse(bars);
    if (!(a > 0)) return null;
    return a * Math.sqrt(n > 0 ? n : 1);
  }, [atr, bars]);

  const r: RRResult = useMemo(
    () =>
      computeTradeRR({
        side,
        entry: parse(entry),
        stop: parse(stop),
        target: parse(target),
        tickSize: ts,
        tickValue: tv,
        contracts: parse(contracts) > 0 ? parse(contracts) : 1,
        costPerContract: parse(commission) > 0 ? parse(commission) : 0,
        slippageTicks: parse(slippage) > 0 ? parse(slippage) : 0,
        horizonSigma,
        horizonDrift: Number.isFinite(parse(drift)) ? parse(drift) : 0,
        assumedWinRate: parse(winRate) > 0 ? parse(winRate) / 100 : null,
      }),
    [side, entry, stop, target, ts, tv, contracts, commission, slippage, horizonSigma, drift, winRate],
  );

  // Headline probability of tagging the target before the stop (drift-aware if a drift view is given).
  const pWin = r.valid ? (r.winProbSource === "drift" && r.pTargetDrift != null ? r.pTargetDrift : r.pTargetDriftless) : 0;
  const pLose = 1 - pWin;

  const verdictChip =
    r.verdict === "positive"
      ? "border-call/30 bg-call/10 text-call"
      : r.verdict === "negative"
        ? "border-put/30 bg-put/10 text-put"
        : "border-white/10 bg-white/[0.03] text-neutral-300";
  const verdictLabel =
    r.verdict === "positive" ? "Positive expectancy" : r.verdict === "negative" ? "Negative expectancy" : "Fair game · 0 EV";

  const segBtn = (active: boolean, tone: "call" | "put") =>
    `flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition ${
      active
        ? tone === "call"
          ? "bg-call/15 text-call shadow-[inset_0_0_0_1px_rgba(52,211,153,0.4)]"
          : "bg-put/15 text-put shadow-[inset_0_0_0_1px_rgba(248,113,113,0.4)]"
        : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
    }`;

  const srcLabel =
    r.winProbSource === "assumed" ? "your win-rate" : r.winProbSource === "drift" ? "drift model" : "driftless odds";

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      {/* ── Inputs ── */}
      <div className="glass fade-up space-y-4 p-4 sm:p-5">
        <div className="flex gap-2 rounded-xl border border-white/[0.06] bg-white/[0.02] p-1">
          <button type="button" onClick={() => setSide("long")} className={segBtn(side === "long", "call")}>
            ▲ Long
          </button>
          <button type="button" onClick={() => setSide("short")} className={segBtn(side === "short", "put")}>
            ▼ Short
          </button>
        </div>

        <label className="block">
          <span className="lbl">Instrument</span>
          <div className="relative mt-1">
            <select
              value={sym}
              onChange={(e) => setSym(e.target.value)}
              className="w-full appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-2 pl-3 pr-8 text-sm text-neutral-100 outline-none transition hover:border-white/20 focus:border-accent/50"
            >
              {FUTURES.map((f) => (
                <option key={f.symbol} value={f.symbol} className="bg-neutral-900">
                  {f.symbol} · {f.name}
                </option>
              ))}
              <option value="CUSTOM" className="bg-neutral-900">
                Custom contract…
              </option>
            </select>
            <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
              <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
            </svg>
          </div>
          <span className="mt-1 block text-[11px] text-neutral-500">
            {ts > 0 && tv > 0 ? `Tick ${num(ts, 6)} · $${num(tv, 4)}/tick · $${num(pointValue({ tickSize: ts, tickValue: tv }), 2)}/point` : "Set tick size & value"}
          </span>
        </label>

        {!spec && (
          <div className="grid grid-cols-2 gap-2.5">
            <Field label="Tick size" value={tickSize} onChange={setTickSize} placeholder="0.25" />
            <Field label="$ / tick" value={tickValue} onChange={setTickValue} placeholder="12.5" />
          </div>
        )}

        <div className="grid grid-cols-1 gap-2.5">
          <Field label="Entry" value={entry} onChange={setEntry} placeholder="5000" />
          <div className="grid grid-cols-2 gap-2.5">
            <Field label="Stop" value={stop} onChange={setStop} hint={r.valid ? `${num(r.riskTicks, 0)} ticks · ${money(r.riskDollars)}` : undefined} />
            <Field label="Target" value={target} onChange={setTarget} hint={r.valid ? `${num(r.rewardTicks, 0)} ticks · ${money(r.rewardDollars)}` : undefined} />
          </div>
          <Field label="Contracts" value={contracts} onChange={setContracts} placeholder="1" />
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowEdge((v) => !v)}
            className="flex w-full items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs font-medium text-neutral-300 transition hover:border-white/15"
          >
            <span>Costs &amp; edge model (optional)</span>
            <span className={`transition-transform ${showEdge ? "rotate-180" : ""}`}>
              <svg aria-hidden viewBox="0 0 12 12" className="h-3 w-3 text-neutral-500">
                <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
              </svg>
            </span>
          </button>
          {showEdge && (
            <div className="mt-3 space-y-3 border-l border-white/[0.06] pl-3">
              <div className="grid grid-cols-2 gap-2.5">
                <Field label="Commission" value={commission} onChange={setCommission} placeholder="0" suffix="$/RT" hint="round-trip, per contract" />
                <Field label="Slippage" value={slippage} onChange={setSlippage} placeholder="0" suffix="ticks" hint="per fill" />
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                <Field label="Volatility" value={atr} onChange={setAtr} placeholder="0" suffix="ATR" hint="points per bar" />
                <Field label="Horizon" value={bars} onChange={setBars} placeholder="1" suffix="bars" hint="to resolve" />
              </div>
              <Field
                label="Drift / bias"
                value={drift}
                onChange={setDrift}
                placeholder="0"
                suffix="pts"
                hint={horizonSigma != null ? `expected net move over horizon · 1σ ≈ ${num(horizonSigma, 1)} pts` : "needs a volatility to matter"}
              />
              <Field label="Your win rate" value={winRate} onChange={setWinRate} placeholder="—" suffix="%" hint="from your journal — overrides the model for EV" />
            </div>
          )}
        </div>
      </div>

      {/* ── Results ── */}
      <div className="space-y-4">
        {!r.valid ? (
          <div className="glass fade-up flex items-start gap-3 p-5" role="alert">
            <svg aria-hidden viewBox="0 0 16 16" className="mt-0.5 h-4 w-4 shrink-0 text-put">
              <path fill="currentColor" d="M8 1.5 15 14H1L8 1.5Zm-.75 5v4h1.5v-4h-1.5Zm0 5v1.5h1.5V11.5h-1.5Z" />
            </svg>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-put">Check the trade</div>
              <div className="mt-0.5 text-sm text-neutral-300">{r.reason}</div>
            </div>
          </div>
        ) : (
          <>
            {/* Headline */}
            <div className="glass fade-up p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="lbl mb-1">Risk : Reward</div>
                  <div className="display text-4xl leading-none text-neutral-50">
                    1 : {num(r.grossRR, 2)}
                  </div>
                  <div className="mt-1.5 text-[11px] text-neutral-500">
                    risk {num(r.riskPoints, 2)} pts → reward {num(r.rewardPoints, 2)} pts
                    {r.costTotal > 0 && <> · net {num(r.netRR, 2)}:1 after costs</>}
                  </div>
                </div>
                <div className="text-right">
                  <div className="lbl mb-1">P(hit target first)</div>
                  <div className={`display text-4xl leading-none ${pWin >= r.breakevenWinRate ? "text-call" : "text-put"}`}>{pct(pWin, 1)}</div>
                  <div className="mt-1.5 text-[11px] text-neutral-500">before the stop · {srcLabel}</div>
                </div>
              </div>

              {/* Probability split bar: target-first vs stop-first */}
              <div className="mt-4">
                <div className="flex h-7 overflow-hidden rounded-lg border border-white/[0.06]">
                  <div className="flex items-center justify-center bg-call/25 text-[11px] font-semibold text-call transition-all" style={{ width: `${Math.max(6, pWin * 100)}%` }}>
                    {pWin >= 0.14 ? pct(pWin, 0) : ""}
                  </div>
                  <div className="flex items-center justify-center bg-put/25 text-[11px] font-semibold text-put transition-all" style={{ width: `${Math.max(6, pLose * 100)}%` }}>
                    {pLose >= 0.14 ? pct(pLose, 0) : ""}
                  </div>
                </div>
                <div className="mt-1.5 flex justify-between text-[11px] text-neutral-500">
                  <span>Target first</span>
                  <span>Stop first</span>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-white/[0.05] pt-3">
                <span className="text-xs text-neutral-400">
                  Break-even hit-rate <span className="font-mono text-neutral-200">{pct(r.breakevenWinRate, 1)}</span>
                </span>
                <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${verdictChip}`}>{verdictLabel}</span>
              </div>
            </div>

            {/* Stat grid */}
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              <Stat label="Risk" value={money(r.riskDollars)} tone="put" sub={`${num(r.riskTicks, 0)} ticks`} />
              <Stat label="Reward" value={money(r.rewardDollars)} tone="call" sub={`${num(r.rewardTicks, 0)} ticks`} />
              <Stat label="Expectancy / trade" value={money(r.expectancyDollars)} tone={r.expectancyDollars >= 0 ? "call" : "put"} sub={`${r.expectancyR >= 0 ? "+" : ""}${num(r.expectancyR, 2)}R`} />
              <Stat label="Edge vs break-even" value={`${r.edge >= 0 ? "+" : ""}${pct(r.edge, 1)}`} tone={r.edge >= 0 ? "call" : "put"} sub={`win ${pct(r.winProb, 0)} vs need ${pct(r.breakevenWinRate, 0)}`} />
              <Stat label="Kelly stake" value={pct(r.kelly, 1)} sub={`¼-Kelly ${pct(r.kelly / 4, 1)}`} />
              <Stat label="Cost drag" value={money(r.costTotal)} sub={r.costTotal > 0 ? "round trip" : "none set"} />
            </div>

            {/* Insight */}
            <div className="glass p-4 sm:p-5">
              <div className="lbl mb-2">The read</div>
              {r.winProbSource === "driftless" ? (
                <p className="text-sm leading-relaxed text-neutral-300">
                  At driftless odds this exact bracket tags the target first <span className="font-semibold text-neutral-100">{pct(r.pTargetDriftless, 1)}</span> of the
                  time — <span className="font-semibold text-neutral-100">exactly</span> the {pct(r.breakevenWinRate, 1)} you need to break even. A market with no
                  directional edge makes R:R a <span className="text-neutral-100">fair game</span>: widening the target lowers your hit-rate one-for-one.{" "}
                  {r.costTotal > 0 ? (
                    <>Costs of {money(r.costTotal)} tip it slightly negative.</>
                  ) : (
                    <>Add your win rate or a drift view on the left to test for a real edge.</>
                  )}
                </p>
              ) : (
                <p className="text-sm leading-relaxed text-neutral-300">
                  Using {srcLabel}, you win <span className="font-semibold text-neutral-100">{pct(r.winProb, 1)}</span> versus a{" "}
                  <span className="font-semibold text-neutral-100">{pct(r.breakevenWinRate, 1)}</span> break-even — an edge of{" "}
                  <span className={r.edge >= 0 ? "font-semibold text-call" : "font-semibold text-put"}>
                    {r.edge >= 0 ? "+" : ""}
                    {pct(r.edge, 1)}
                  </span>
                  . Over 100 trades that compounds to{" "}
                  <span className={r.expectancyDollars >= 0 ? "font-semibold text-call" : "font-semibold text-put"}>{money(r.expectancyDollars * 100)}</span>{" "}
                  at this size. {r.kelly > 0 ? <>Full-Kelly says risk {pct(r.kelly, 1)} of capital per trade — most run a quarter of that.</> : <>Negative edge — Kelly says don&apos;t take it.</>}
                </p>
              )}
            </div>

            {/* Finite-horizon touch odds */}
            {horizonSigma != null && r.pTouchTarget != null && (
              <div className="glass p-4 sm:p-5">
                <div className="mb-3 flex items-end justify-between">
                  <div className="lbl">Within your horizon · 1σ ≈ {num(horizonSigma, 1)} pts</div>
                  <span className="text-[11px] text-neutral-500">reflection principle</span>
                </div>
                <div className="grid grid-cols-3 gap-2.5">
                  <Stat label="Touch target" value={pct(r.pTouchTarget, 0)} tone="call" sub="tags TP at all" />
                  <Stat label="Touch stop" value={pct(r.pTouchStop, 0)} tone="put" sub="tags SL at all" />
                  <Stat label="Close beyond TP" value={pct(r.pCloseBeyondTarget, 0)} sub="at horizon end" />
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">
                  These count each barrier independently over the holding window — both can be touched, so they need not sum to one. The headline P(target
                  first) above is the true race between them.
                </p>
              </div>
            )}

            <p className="text-[11px] leading-relaxed text-neutral-600">
              Probabilities assume price moves as arithmetic Brownian motion between your levels — a clean baseline, not a market forecast. Real fills gap,
              trend and mean-revert. Educational tooling, not financial advice.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
