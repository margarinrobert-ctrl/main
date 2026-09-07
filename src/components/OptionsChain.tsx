"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { fmtUsd, netGex } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

function n2(n: number | null | undefined): string {
  return n == null ? "—" : n.toFixed(2);
}
function ivPct(n: number | null | undefined): string {
  return n == null ? "—" : `${(n * 100).toFixed(1)}%`;
}
function iv(n: number | null | undefined): string {
  return n == null ? "—" : n.toFixed(2);
}
function loc(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString();
}

function Pill({ children }: { children: ReactNode }) {
  return <span className="chip">{children}</span>;
}

export function OptionsChain({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [selectedExp, setSelectedExp] = useState("");
  const [showFull, setShowFull] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const res = await loadChain(symbol);
        if (cancelled) return;
        setChain(res.chain);
        setSpot(res.spot);
        setAsOf(res.asOf);
        setSource(res.source);
        setState(res.chain.length ? "ok" : "empty");
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

  const expirations = useMemo(() => Array.from(new Set(chain.map((c) => c.expiration))).sort(), [chain]);

  useEffect(() => {
    if (expirations.length === 0) return;
    if (expirations.includes(selectedExp)) return;
    // default to the nearest non-expired expiration
    const withDte = expirations.map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }));
    const future = withDte.filter((x) => (x.dte ?? 0) >= 0).sort((a, b) => (a.dte ?? 0) - (b.dte ?? 0));
    setSelectedExp((future[0] ?? withDte[0]).e);
  }, [expirations, chain, selectedExp]);

  // Honor the dashboard-wide expiration selector (overrides the local default).
  useEffect(() => {
    if (exp && exp !== "ALL" && chain.some((c) => c.expiration === exp)) setSelectedExp(exp);
  }, [exp, chain]);

  const gex = useMemo(() => netGex(chain, spot), [chain, spot]);

  const { rows, strikeCount } = useMemo(() => {
    const byStrike = new Map<number, { call?: OptionContract; put?: OptionContract }>();
    for (const c of chain) {
      if (c.expiration !== selectedExp) continue;
      const e = byStrike.get(c.strike) ?? {};
      if (c.type === "call") e.call = c;
      else e.put = c;
      byStrike.set(c.strike, e);
    }
    let strikes = [...byStrike.keys()].sort((a, b) => a - b);
    const count = strikes.length;
    if (!showFull && spot != null && strikes.length > 25) {
      let idx = 0;
      let best = Infinity;
      strikes.forEach((s, i) => {
        const d = Math.abs(s - spot);
        if (d < best) {
          best = d;
          idx = i;
        }
      });
      strikes = strikes.slice(Math.max(0, idx - 12), Math.min(strikes.length, idx + 13));
    }
    return { rows: strikes.map((k) => ({ strike: k, ...byStrike.get(k)! })), strikeCount: count };
  }, [chain, selectedExp, showFull, spot]);

  const callBg = (c?: OptionContract) =>
    c && c.delta != null ? { backgroundColor: `rgba(52,211,153,${0.04 + 0.34 * Math.min(0.9, Math.abs(c.delta))})` } : undefined;
  const putBg = (c?: OptionContract) =>
    c && c.delta != null ? { backgroundColor: `rgba(248,113,113,${0.04 + 0.3 * Math.min(0.9, Math.abs(c.delta))})` } : undefined;

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader
        eyebrow="Options chain"
        title={symbol}
        right={
          gex != null ? (
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${gex >= 0 ? "border-call/30 bg-call/10 text-call" : "border-put/30 bg-put/10 text-put"}`}
            >
              {gex >= 0 ? "Long gamma · mean-reverting" : "Short gamma · trend-amplifying"} · {fmtUsd(gex)}/1%
            </span>
          ) : undefined
        }
      />

      {state === "loading" && <Loading label="Loading options chain…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options chain returned." />}
      {state === "ok" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Pill>Spot {spot != null ? spot.toLocaleString() : "—"}</Pill>
            <span className="chip gap-1">
              Exp
              <select
                value={selectedExp}
                onChange={(e) => setSelectedExp(e.target.value)}
                aria-label="Expiration"
                className="bg-transparent py-1 text-neutral-100 outline-none"
              >
                {expirations.map((e) => (
                  <option key={e} value={e} className="bg-neutral-900">
                    {e}
                  </option>
                ))}
              </select>
            </span>
            <Pill>{strikeCount} strikes</Pill>
            {asOf && <Pill>Updated {asOf.slice(11, 16)}Z</Pill>}
            <button
              type="button"
              onClick={() => setShowFull((v) => !v)}
              aria-pressed={showFull}
              className={`ml-auto rounded-lg border px-3 py-2 text-xs font-medium transition ${
                showFull ? "border-accent/40 bg-accent/10 text-accent-bright" : "border-white/10 bg-white/[0.03] text-neutral-400 hover:border-white/20 hover:text-neutral-200"
              }`}
            >
              {showFull ? "Full chain" : "Around spot"}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs tabular-nums">
              <thead>
                <tr>
                  <th className="lbl px-2 py-1.5 !text-center text-call" colSpan={7}>
                    Calls
                  </th>
                  <th className="lbl px-2 py-1.5 !text-center text-neutral-200">Strike</th>
                  <th className="lbl px-2 py-1.5 !text-center text-put" colSpan={7}>
                    Puts
                  </th>
                </tr>
                <tr className="border-b border-white/[0.08]">
                  {["IV", "Δ", "Vol", "OI", "Bid", "Ask", "Last"].map((h) => (
                    <th key={`c${h}`} className="lbl px-2 py-1.5 !text-right">
                      {h}
                    </th>
                  ))}
                  <th className="px-2 py-1.5 text-center font-normal text-neutral-600">·</th>
                  {["Last", "Bid", "Ask", "OI", "Vol", "Δ", "IV"].map((h) => (
                    <th key={`p${h}`} className="lbl px-2 py-1.5 !text-right">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ strike, call, put }) => {
                  const atm = spot != null && rows.length > 1;
                  const isAtm = atm && Math.abs(strike - (spot ?? 0)) === Math.min(...rows.map((r) => Math.abs(r.strike - (spot ?? 0))));
                  return (
                    <tr key={strike} className="border-b border-white/[0.04] transition-colors hover:bg-white/[0.02]">
                      <td className="px-2 py-1" style={callBg(call)}>{ivPct(call?.impliedVolatility)}</td>
                      <td className="px-2 py-1" style={callBg(call)}>{n2(call?.delta)}</td>
                      <td className="px-2 py-1" style={callBg(call)}>{loc(call?.volume)}</td>
                      <td className="px-2 py-1" style={callBg(call)}>{loc(call?.openInterest)}</td>
                      <td className="px-2 py-1" style={callBg(call)}>{n2(call?.bid)}</td>
                      <td className="px-2 py-1" style={callBg(call)}>{n2(call?.ask)}</td>
                      <td className="px-2 py-1" style={callBg(call)}>{n2(call?.last)}</td>
                      <td className={`px-2 py-1 text-center font-mono font-semibold ${isAtm ? "bg-accent/[0.12] text-accent-bright shadow-[inset_0_0_0_1px_rgba(52,211,153,0.35)]" : "text-neutral-200"}`}>
                        {strike}
                      </td>
                      <td className="px-2 py-1" style={putBg(put)}>{n2(put?.last)}</td>
                      <td className="px-2 py-1" style={putBg(put)}>{n2(put?.bid)}</td>
                      <td className="px-2 py-1" style={putBg(put)}>{n2(put?.ask)}</td>
                      <td className="px-2 py-1" style={putBg(put)}>{loc(put?.openInterest)}</td>
                      <td className="px-2 py-1" style={putBg(put)}>{loc(put?.volume)}</td>
                      <td className="px-2 py-1" style={putBg(put)}>{n2(put?.delta)}</td>
                      <td className="px-2 py-1" style={putBg(put)}>{iv(put?.impliedVolatility)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
