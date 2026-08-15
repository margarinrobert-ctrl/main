"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain } from "@/lib/client-data";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { bsImpliedVol, bsQuote, valueCurve, type OptType } from "@/lib/quant/bs";
import { scanStrikes, type TradeEval } from "@/lib/quant/strategy";
import { useChartFrame } from "./chartFrame";
import { EmptyState, ErrorState, Loading, SectionHeader, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const CAL_DAYS = 365;
const num = (s: string): number | null => {
  const v = Number(s);
  return Number.isFinite(v) ? v : null;
};
const px2 = (v: number) => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const g4 = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 4 });

const mid = (c: OptionContract): number | null =>
  c.bid != null && c.ask != null && c.ask > 0 && c.ask >= c.bid ? (c.bid + c.ask) / 2 : c.last != null && c.last > 0 ? c.last : null;

const field =
  "w-full rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-right font-mono text-xs text-neutral-100 outline-none transition hover:border-white/20 focus:border-accent/50";

function Input({ label, value, onChange, suffix }: { label: string; value: string; onChange: (v: string) => void; suffix?: string }) {
  return (
    <label className="block">
      <span className="lbl px-0.5">{label}</span>
      <div className="relative mt-1">
        <input value={value} onChange={(e) => onChange(e.target.value)} inputMode="decimal" className={`${field} ${suffix ? "pr-8" : ""}`} aria-label={label} />
        {suffix && <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-neutral-500">{suffix}</span>}
      </div>
    </label>
  );
}

export function BsLab({ symbol }: { symbol: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const frame = useChartFrame(`${symbol} BS lab`);

  // model inputs (strings so partial typing works)
  const [type, setType] = useState<OptType>("call");
  const [sS, setS] = useState("100");
  const [sK, setK] = useState("100");
  const [sDte, setDte] = useState("30");
  const [sVol, setVol] = useState("20");
  const [sR, setR] = useState("4.5");
  const [sQ, setQ] = useState("1.2");
  const [picked, setPicked] = useState<OptionContract | null>(null);
  // trade-scanner scenario: the vol you believe will REALIZE and the drift you assume
  const [sigmaScan, setSigmaScan] = useState("");
  const [muScan, setMuScan] = useState("0");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      setPicked(null);
      try {
        const res = await loadChain(symbol);
        if (cancelled) return;
        setChain(res.chain);
        setSpot(res.spot);
        if (res.spot != null) {
          setS(String(Math.round(res.spot * 100) / 100));
          setK(String(Math.round(res.spot)));
        }
        setState(res.chain.length ? "ok" : "empty");
        const exps0 = [...new Map(res.chain.map((c) => [c.expiration, c.dte])).entries()]
          .filter(([, d]) => d != null && (d as number) >= 0)
          .sort((a, b) => (a[1] as number) - (b[1] as number));
        for (const [e] of exps0) {
          const iv = res.chain.find((c) => c.expiration === e && c.impliedVolatility != null && c.impliedVolatility > 0)?.impliedVolatility;
          if (iv) {
            setSigmaScan((iv * 100).toFixed(1));
            break;
          }
        }
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

  const expirations = useMemo(
    () =>
      [...new Map(chain.map((c) => [c.expiration, c.dte])).entries()]
        .filter(([, dte]) => dte != null && dte >= 0)
        .sort((a, b) => (a[1] as number) - (b[1] as number)),
    [chain],
  );
  const [pickExp, setPickExp] = useState("");
  useEffect(() => setPickExp(expirations[0]?.[0] ?? ""), [expirations]);

  const pickStrikes = useMemo(() => {
    if (!pickExp || spot == null) return [] as number[];
    const ks = [...new Set(chain.filter((c) => c.expiration === pickExp).map((c) => c.strike))].sort((a, b) => a - b);
    const iAtm = ks.reduce((best, k, i) => (Math.abs(k - spot) < Math.abs(ks[best] - spot) ? i : best), 0);
    return ks.slice(Math.max(0, iAtm - 12), iAtm + 13);
  }, [chain, pickExp, spot]);

  const applyContract = (strike: number, t: OptType) => {
    const c = chain.find((x) => x.expiration === pickExp && x.strike === strike && x.type === t);
    if (!c) return;
    setPicked(c);
    setType(t);
    if (spot != null) setS(String(Math.round(spot * 10000) / 10000));
    setK(String(c.strike));
    setDte(String(Math.max(c.dte ?? 0, 0.5)));
    const iv = c.impliedVolatility != null && c.impliedVolatility > 0 ? c.impliedVolatility : null;
    if (iv != null) setVol((iv * 100).toFixed(2));
  };

  // parsed inputs → model
  const S = num(sS);
  const K = num(sK);
  const dte = num(sDte);
  const vol = num(sVol);
  const inputs = useMemo(() => {
    if (S == null || K == null || dte == null || vol == null || S <= 0 || K <= 0 || dte <= 0 || vol <= 0) return null;
    return { type, spot: S, strike: K, tYears: dte / CAL_DAYS, sigma: vol / 100, r: (num(sR) ?? 0) / 100, q: (num(sQ) ?? 0) / 100 };
  }, [type, S, K, dte, vol, sR, sQ]);

  const quote = useMemo(() => (inputs ? bsQuote(inputs) : null), [inputs]);
  const curve = useMemo(() => (inputs ? valueCurve(inputs) : []), [inputs]);

  // market comparison for the picked contract
  const marketMid = picked ? mid(picked) : null;
  const solvedIv = useMemo(() => {
    if (!inputs || marketMid == null) return null;
    return bsImpliedVol({ type: inputs.type, spot: inputs.spot, strike: inputs.strike, tYears: inputs.tYears, r: inputs.r, q: inputs.q }, marketMid);
  }, [inputs, marketMid]);

  const breakeven = quote && K != null ? (type === "call" ? K + quote.price : K - quote.price) : null;

  // per-strike trade scanner over the picked expiry, under the explicit scenario
  const scan = useMemo(() => {
    const sig = (num(sigmaScan) ?? 0) / 100;
    if (!pickExp || spot == null || sig <= 0) return [];
    return scanStrikes(
      chain.filter((c) => c.expiration === pickExp),
      spot,
      { sigma: sig, mu: (num(muScan) ?? 0) / 100, r: (num(sR) ?? 0) / 100, q: (num(sQ) ?? 0) / 100 },
    );
  }, [chain, pickExp, spot, sigmaScan, muScan, sR, sQ]);
  const bestOverall = useMemo(() => {
    let b: { strike: number; t: TradeEval } | null = null;
    for (const row of scan) for (const t of row.trades) if (!b || t.expPnl > b.t.expPnl) b = { strike: row.strike, t };
    return b;
  }, [scan]);
  const bestDefined = useMemo(() => {
    let b: { strike: number; t: TradeEval } | null = null;
    for (const row of scan) for (const t of row.trades) if (Number.isFinite(t.maxLoss) && t.kind.startsWith("long") && (!b || t.expPnl > b.t.expPnl)) b = { strike: row.strike, t };
    return b;
  }, [scan]);
  const atmStrike = useMemo(() => (scan.length && spot != null ? scan.reduce((p, c2) => (Math.abs(c2.strike - spot) < Math.abs(p.strike - spot) ? c2 : p)).strike : null), [scan, spot]);
  const tradeName: Record<string, string> = { "long-call": "Long call", "short-call": "Short call", "long-put": "Long put", "short-put": "Short put" };
  const tradeChip = (k: string) =>
    k === "short-put" || k === "long-call" ? "border-call/30 bg-call/10 text-call" : k === "short-call" || k === "long-put" ? "border-put/30 bg-put/10 text-put" : "border-white/10 text-neutral-300";

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <SectionHeader eyebrow="Black-Scholes lab" title={symbol} right={<div className="flex items-center gap-2"><span className="lbl">pricer · greeks · implied vol</span>{frame.controls}</div>} />

      {state === "loading" && <Loading label="Loading chain…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No chain loaded — use manual inputs on a ticker with options data." />}
      {state === "ok" && (
        <>
          {/* Contract picker */}
          <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
            <div className="lbl mb-2">Load a live contract (fills the model below)</div>
            <div className="flex flex-wrap items-center gap-2">
              <select value={pickExp} onChange={(e) => setPickExp(e.target.value)} aria-label="Expiration" className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-neutral-100 outline-none hover:border-white/20">
                {expirations.map(([e, dte]) => (
                  <option key={e} value={e} className="bg-neutral-900">
                    {dte != null && dte <= 0 ? "0DTE" : `${dte}d`} · {e}
                  </option>
                ))}
              </select>
              <select
                value=""
                onChange={(e) => {
                  const [k, t] = e.target.value.split("|");
                  if (k) applyContract(Number(k), t as OptType);
                }}
                aria-label="Contract"
                className="min-w-44 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-neutral-100 outline-none hover:border-white/20"
              >
                <option value="" className="bg-neutral-900">
                  Pick strike…
                </option>
                {pickStrikes.map((k) => (
                  <optgroup key={k} label={`Strike ${k}`} className="bg-neutral-900">
                    <option value={`${k}|call`} className="bg-neutral-900">{`${k} Call`}</option>
                    <option value={`${k}|put`} className="bg-neutral-900">{`${k} Put`}</option>
                  </optgroup>
                ))}
              </select>
              {picked && (
                <span className="lbl">
                  loaded {picked.strike} {picked.type} · {picked.expiration}
                  {marketMid != null ? ` · market mid $${px2(marketMid)}` : " · no live quote"}
                </span>
              )}
            </div>
          </div>

          {/* Model inputs */}
          <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-7">
            <label className="block">
              <span className="lbl px-0.5">Type</span>
              <div className="mt-1 flex overflow-hidden rounded-lg border border-white/10">
                {(["call", "put"] as const).map((t) => (
                  <button key={t} onClick={() => setType(t)} aria-pressed={type === t} className={`flex-1 px-2 py-1.5 text-xs font-semibold uppercase transition ${type === t ? (t === "call" ? "bg-call/20 text-call" : "bg-put/20 text-put") : "bg-white/[0.02] text-neutral-500 hover:text-neutral-300"}`}>
                    {t}
                  </button>
                ))}
              </div>
            </label>
            <Input label="Spot" value={sS} onChange={setS} />
            <Input label="Strike" value={sK} onChange={setK} />
            <Input label="DTE" value={sDte} onChange={setDte} suffix="d" />
            <Input label="Vol σ" value={sVol} onChange={setVol} suffix="%" />
            <Input label="Rate r" value={sR} onChange={setR} suffix="%" />
            <Input label="Div q" value={sQ} onChange={setQ} suffix="%" />
          </div>

          {!quote || !inputs ? (
            <div className="mt-4">
              <EmptyState label="Enter valid inputs (spot, strike, DTE and vol must be positive)." />
            </div>
          ) : (
            <>
              {/* Price + market comparison */}
              <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <Stat label="BS fair value" value={`$${px2(quote.price)}`} sub={`intrinsic $${px2(quote.intrinsic)} + time $${px2(quote.timeValue)}`} tone={type === "call" ? "call" : "put"} />
                <Stat label="Market mid" value={marketMid == null ? "—" : `$${px2(marketMid)}`} sub={picked ? (marketMid != null ? `model ${quote.price >= marketMid ? "+" : ""}${px2(quote.price - marketMid)} vs mid` : "no quote") : "load a contract"} />
                <Stat label="Implied vol (solved)" value={solvedIv == null ? "—" : `${(solvedIv * 100).toFixed(2)}%`} sub={picked?.impliedVolatility ? `vendor ${(picked.impliedVolatility * 100).toFixed(2)}%` : "from market mid"} />
                <Stat label="P(expire ITM)" value={`${(quote.probItm * 100).toFixed(1)}%`} sub={`risk-neutral N(${type === "call" ? "" : "−"}d2)`} />
              </div>

              {/* Greeks */}
              <div className="mt-2.5 grid grid-cols-2 gap-2.5 sm:grid-cols-6">
                <Stat label="Delta Δ" value={g4(quote.delta)} sub="per $1 spot" />
                <Stat label="Gamma Γ" value={g4(quote.gamma)} sub="ΔΔ per $1" />
                <Stat label="Vega ν" value={`$${g4(quote.vega)}`} sub="per 1 vol pt" />
                <Stat label="Theta Θ" value={`$${g4(quote.thetaDay)}`} sub="per day" tone={quote.thetaDay < 0 ? "put" : "call"} />
                <Stat label="Rho ρ" value={`$${g4(quote.rho)}`} sub="per 1 rate pt" />
                <Stat label="Vanna" value={`${g4(quote.vanna)}`} sub="Δ per 1 vol pt" />
              </div>

              {/* Value curve */}
              <div className="mt-4">
                <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                  <span className="lbl">Value vs spot · today (σ={sVol}%, {sDte}d) against expiry payoff</span>
                  <span className="lbl">d1 {quote.d1.toFixed(3)} · d2 {quote.d2.toFixed(3)}{breakeven != null ? ` · breakeven ${px2(breakeven)}` : ""}</span>
                </div>
                <div className={`${frame.expanded ? "h-[42vh]" : "h-[280px]"} w-full`}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={curve} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
                      <CartesianGrid {...GRID_PROPS} />
                      <XAxis dataKey="spot" {...AXIS_PROPS} tickFormatter={(v) => Math.round(Number(v)).toString()} minTickGap={36} type="number" domain={["dataMin", "dataMax"]} />
                      <YAxis {...AXIS_PROPS} width={52} tickFormatter={(v) => `$${Number(v).toFixed(0)}`} />
                      <Tooltip {...TOOLTIP_PROPS} cursor={TOOLTIP_CURSOR_LINE} formatter={(v: number | string, n) => [`$${px2(Number(v))}`, n]} labelFormatter={(l) => `Spot ${px2(Number(l))}`} />
                      <ReferenceLine x={inputs.strike} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 3" label={{ value: "K", fill: "#9ca3af", fontSize: 10, position: "top" }} />
                      {S != null && <ReferenceLine x={S} stroke="#22d3ee" strokeDasharray="3 3" label={{ value: "spot", fill: "#22d3ee", fontSize: 10, position: "top" }} />}
                      {breakeven != null && <ReferenceLine x={breakeven} stroke="#fbbf24" strokeDasharray="3 3" label={{ value: "b/e", fill: "#fbbf24", fontSize: 10, position: "insideTopRight" }} />}
                      <Line type="monotone" dataKey="payoff" name="Payoff at expiry" stroke="#737373" strokeDasharray="5 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                      <Line type="monotone" dataKey="value" name="BS value today" stroke={type === "call" ? CHART.call : CHART.put} strokeWidth={2.2} dot={false} isAnimationActive={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Per-strike trade scanner */}
              <div className="mt-5 border-t border-white/[0.05] pt-4">
                <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <div className="lbl">Trade scanner · {pickExp || "front expiry"}</div>
                    <h3 className="display mt-0.5 text-sm text-neutral-100">Expected P&L and win rate per strike, at live mids</h3>
                  </div>
                  <div className="flex items-end gap-2">
                    <label className="block w-24">
                      <span className="lbl px-0.5">Scenario σ</span>
                      <div className="relative mt-1">
                        <input value={sigmaScan} onChange={(e) => setSigmaScan(e.target.value)} inputMode="decimal" aria-label="Scenario vol" className={`${field} pr-8`} />
                        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-neutral-500">%</span>
                      </div>
                    </label>
                    <label className="block w-24">
                      <span className="lbl px-0.5">Drift μ</span>
                      <div className="relative mt-1">
                        <input value={muScan} onChange={(e) => setMuScan(e.target.value)} inputMode="decimal" aria-label="Scenario drift" className={`${field} pr-10`} />
                        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-neutral-500">%/yr</span>
                      </div>
                    </label>
                    <button
                      onClick={() => setMuScan(String(Math.round(((num(sR) ?? 0) - (num(sQ) ?? 0)) * 100) / 100))}
                      className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[11px] text-neutral-400 transition hover:border-white/20 hover:text-neutral-200"
                      title="Set drift to r − q (risk-neutral): market-fair prices then show ~zero EV"
                    >
                      risk-neutral
                    </button>
                  </div>
                </div>

                {!scan.length ? (
                  <EmptyState label="No scannable quotes for this expiry." hint="The scanner needs live bid/ask mids and a positive scenario vol." />
                ) : (
                  <>
                    <div className="mb-3 grid gap-2.5 sm:grid-cols-2">
                      {bestOverall && (
                        <div className="rounded-xl border border-call/25 bg-call/[0.05] p-3.5">
                          <div className="lbl mb-1 text-call">Highest expected P&L (any risk)</div>
                          <p className="text-sm leading-relaxed text-neutral-300">
                            <span className={`mr-1.5 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tradeChip(bestOverall.t.kind)}`}>{tradeName[bestOverall.t.kind]}</span>
                            <span className="font-mono">{bestOverall.strike}</span> · E[P&L] <span className="font-mono text-call">${px2(bestOverall.t.expPnl * 100)}</span>/ct · win{" "}
                            <span className="font-mono">{(bestOverall.t.winRate * 100).toFixed(0)}%</span> · max loss{" "}
                            <span className="font-mono text-put">{Number.isFinite(bestOverall.t.maxLoss) ? `$${px2(bestOverall.t.maxLoss * 100)}` : "uncapped"}</span>
                          </p>
                        </div>
                      )}
                      {bestDefined && (
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
                          <div className="lbl mb-1">Best defined-risk (long premium)</div>
                          <p className="text-sm leading-relaxed text-neutral-300">
                            <span className={`mr-1.5 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tradeChip(bestDefined.t.kind)}`}>{tradeName[bestDefined.t.kind]}</span>
                            <span className="font-mono">{bestDefined.strike}</span> · E[P&L] <span className={`font-mono ${bestDefined.t.expPnl >= 0 ? "text-call" : "text-put"}`}>${px2(bestDefined.t.expPnl * 100)}</span>/ct · win{" "}
                            <span className="font-mono">{(bestDefined.t.winRate * 100).toFixed(0)}%</span> · max loss <span className="font-mono">${px2(bestDefined.t.maxLoss * 100)}</span>
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="overflow-x-auto rounded-xl border border-white/[0.08]">
                      <table className="tbl w-full">
                        <thead>
                          <tr>
                            <th className="!text-right">Strike</th>
                            <th className="!text-right">Mkt IV C/P</th>
                            <th>Best trade</th>
                            <th className="!text-right">Mid</th>
                            <th className="!text-right">Win rate</th>
                            <th className="!text-right">E[P&L]/ct</th>
                            <th className="!text-right">Max loss/ct</th>
                            <th className="!text-right">B/E</th>
                          </tr>
                        </thead>
                        <tbody className="font-mono tabular-nums">
                          {scan.map((row) => (
                            <tr key={row.strike} className={row.strike === atmStrike ? "bg-accent/[0.05]" : ""}>
                              <td className="text-right font-semibold text-neutral-100">{row.strike}</td>
                              <td className="text-right text-neutral-400">
                                {row.callIv != null ? (row.callIv * 100).toFixed(1) : "—"}/{row.putIv != null ? (row.putIv * 100).toFixed(1) : "—"}
                              </td>
                              <td>
                                {row.best ? (
                                  <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tradeChip(row.best.kind)}`}>{tradeName[row.best.kind]}</span>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td className="text-right text-neutral-300">{row.best ? `$${px2(row.best.premium)}` : "—"}</td>
                              <td className="text-right text-neutral-200">{row.best ? `${(row.best.winRate * 100).toFixed(0)}%` : "—"}</td>
                              <td className={`text-right ${row.best && row.best.expPnl >= 0 ? "text-call" : "text-put"}`}>{row.best ? `$${px2(row.best.expPnl * 100)}` : "—"}</td>
                              <td className="text-right text-neutral-400">{row.best ? (Number.isFinite(row.best.maxLoss) ? `$${px2(row.best.maxLoss * 100)}` : "∞") : "—"}</td>
                              <td className="text-right text-neutral-400">{row.best ? px2(row.best.breakeven) : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="mt-2 text-[11px] leading-relaxed text-neutral-600">
                      "Best" is CONDITIONAL on your scenario: it means the market's implied vol differs from the σ you typed (scenario σ below implied
                      favors shorts — the variance-risk-premium trade — and above favors longs). Set drift to risk-neutral and σ to each strike's
                      implied and every EV collapses to ≈ 0: the market offers no free trade. Win rate is P(profit), not safety — short legs win often
                      and lose big; max loss is the honest column. Per-contract $ = ×100 shares, at mid (real fills pay spread).
                    </p>
                  </>
                )}
              </div>

              <p className="mt-3 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
                European Black-Scholes-Merton with flat vol and continuous r/q. A gap between model value and the market mid is NOT automatically an
                edge — it usually reflects the vol you typed vs the market's implied, American early-exercise value, discrete dividends, or a stale
                quote. Solve the implied vol from the mid to see the vol the market is actually charging. Educational — not financial advice.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}
