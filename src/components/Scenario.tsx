"use client";

import { useEffect, useMemo, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain } from "@/lib/client-data";
import { fmtUsd } from "@/lib/flow/analytics";
import { scenarioMatrix } from "@/lib/flow/scenario";
import { EmptyState, ErrorState, Loading, SectionHeader, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const pctLabel = (x: number) => `${x > 0 ? "+" : ""}${x}%`;
const volLabel = (x: number) => `${x > 0 ? "+" : ""}${x}`;

/** Compact $ for dense cells: $1.2M / $340K / −$88K. */
function cflow(v: number): string {
  const a = Math.abs(v);
  const s = v < 0 ? "−" : "";
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${Math.round(a / 1e3)}K`;
  return `${s}$${Math.round(a)}`;
}

export function Scenario({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const res = await loadChain(symbol);
        if (cancelled) return;
        setChain(res.chain);
        setSpot(res.spot);
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

  const r = useMemo(() => {
    const sub = exp === "ALL" ? chain : chain.filter((c) => c.expiration === exp);
    return scenarioMatrix(sub, spot);
  }, [chain, spot, exp]);

  const regimeChip =
    r.regime === "long"
      ? "border-call/30 bg-call/10 text-call"
      : r.regime === "short"
        ? "border-put/30 bg-put/10 text-put"
        : "border-white/10 bg-white/[0.03] text-neutral-300";

  // Cell background: direction (buy emerald / sell red), intensity by |flow| vs max.
  const cellStyle = (flow: number) => {
    const t = r.maxAbsFlow > 0 ? Math.abs(flow) / r.maxAbsFlow : 0;
    const a = flow === 0 ? 0 : 0.08 + Math.pow(t, 0.8) * 0.8;
    const rgb = flow >= 0 ? "52,211,153" : "248,113,113";
    return { backgroundColor: `rgba(${rgb},${a.toFixed(3)})`, color: t > 0.55 ? "#04140d" : "#d4d4d8" };
  };

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader
        eyebrow="Dealer scenario matrix"
        title={symbol}
        right={
          r.ok ? (
            <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${regimeChip}`}>
              {r.regime === "long" ? "Long γ · dampening" : r.regime === "short" ? "Short γ · amplifying" : "Neutral γ"}
            </span>
          ) : undefined
        }
      />

      {state === "loading" && <Loading label="Loading scenario matrix…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for scenario analysis." />}
      {state === "ok" && !r.ok && <EmptyState label="Greeks unavailable — scenario flows need dealer gamma/vanna." />}
      {state === "ok" && r.ok && (
        <>
          {/* Readouts */}
          <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Net GEX" value={r.netGex == null ? "—" : `${fmtUsd(r.netGex)}/1%`} tone={r.netGex == null ? undefined : r.netGex >= 0 ? "call" : "put"} />
            <Stat
              label="Gamma flip"
              value={r.flip == null ? "—" : `$${r.flip.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              sub={r.flipDistPct == null ? undefined : `${r.flipDistPct >= 0 ? "+" : ""}${r.flipDistPct.toFixed(2)}% away`}
            />
            <Stat label="Net vanna" value={r.vanna == null ? "—" : `${fmtUsd(r.vanna)}/vol-pt`} sub="Δ per IV point" />
            <Stat label="Net charm" value={r.charm == null ? "—" : `${fmtUsd(r.charm)}/d`} sub="daily Δ drift" />
            <Stat label="Net DEX" value={r.netDex == null ? "—" : fmtUsd(r.netDex)} />
          </div>

          {/* Heatmap grid */}
          <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr>
                  <th className="lbl sticky left-0 z-10 bg-[#0a0b10] px-3 py-2 text-left">IV \ Spot</th>
                  {r.spotAxis.map((x) => (
                    <th key={x} className={`px-2 py-2 text-center font-mono text-[11px] tabular-nums ${x === 0 ? "text-neutral-200" : "text-neutral-400"}`}>
                      {pctLabel(x)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {r.cells.map((row, i) => (
                  <tr key={r.volAxis[i]}>
                    <td className={`lbl sticky left-0 z-10 bg-[#0a0b10] px-3 py-1.5 text-left font-mono tabular-nums ${r.volAxis[i] === 0 ? "text-neutral-200" : "text-sky-300/80"}`}>
                      {volLabel(r.volAxis[i])} vp
                    </td>
                    {row.map((cell) => (
                      <td
                        key={cell.spotPct}
                        className={`px-2 py-1.5 text-center font-mono text-[11px] tabular-nums transition-shadow ${cell.amplifies ? "shadow-[inset_0_0_0_1.5px_rgba(255,255,255,0.45)]" : ""}`}
                        style={cellStyle(cell.flow)}
                        title={`Spot ${pctLabel(cell.spotPct)}, IV ${volLabel(cell.volPts)}vp → dealers ${cell.flow >= 0 ? "buy" : "sell"} ${cflow(Math.abs(cell.flow))}${cell.amplifies ? " (amplifies the move)" : cell.spotPct !== 0 ? " (dampens)" : ""}`}
                      >
                        {cell.flow === 0 ? "·" : cflow(cell.flow)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Legend + stress callouts */}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-white/[0.05] pt-3 text-[11px] text-neutral-500">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "rgba(52,211,153,0.75)" }} />Dealers buy (supports)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "rgba(248,113,113,0.75)" }} />Dealers sell (pressures)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm shadow-[inset_0_0_0_1.5px_rgba(255,255,255,0.55)]" />Amplifies the move</span>
          </div>

          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            <div className="rounded-xl border border-put/20 bg-put/[0.05] p-3.5">
              <div className="lbl mb-1 text-put">Worst amplifying scenario</div>
              {r.worst ? (
                <p className="text-sm leading-relaxed text-neutral-300">
                  A <span className="font-mono">{pctLabel(r.worst.spotPct)}</span> move with{" "}
                  <span className="font-mono">{volLabel(r.worst.volPts)}vp</span> IV forces dealers to{" "}
                  <span className={`font-semibold ${r.worst.flow >= 0 ? "text-call" : "text-put"}`}>
                    {r.worst.flow >= 0 ? "buy" : "sell"} {cflow(Math.abs(r.worst.flow))}
                  </span>{" "}
                  into it — the largest destabilizing hedging flow on the grid.
                </p>
              ) : (
                <p className="text-sm leading-relaxed text-neutral-400">
                  No amplifying corner — dealer gamma dampens moves across the grid (long-gamma regime).
                </p>
              )}
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
              <div className="lbl mb-1">Joint stress · gap + vol spike</div>
              {r.stress ? (
                <p className="text-sm leading-relaxed text-neutral-300">
                  A <span className="font-mono">{pctLabel(r.stress.spotPct)}</span> gap with a{" "}
                  <span className="font-mono">{volLabel(r.stress.volPts)}vp</span> vol pop →{" "}
                  <span className={`font-semibold ${r.stress.flow >= 0 ? "text-call" : "text-put"}`}>
                    dealers {r.stress.flow >= 0 ? "buy" : "sell"} {cflow(Math.abs(r.stress.flow))}
                  </span>
                  . Down-gaps arrive with vol spikes, so this corner is the realistic tail.
                </p>
              ) : null}
            </div>
          </div>

          <p className="mt-3 text-[11px] leading-relaxed text-neutral-600">
            Each cell is the dealer re-hedging flow after the shock: −(GEX·spot% + vanna·ΔIV), the $ of delta
            dealers must trade to stay neutral. Charm ({r.charm == null ? "—" : `${fmtUsd(r.charm)}/day`}) is a
            constant drift and is shown above rather than shaded into every cell. Educational — not advice.
          </p>
        </>
      )}
    </div>
  );
}
