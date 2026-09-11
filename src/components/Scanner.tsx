"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { HistoryBar } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { scanRow, type ScanRow } from "@/lib/flow/signals";
import { withBase } from "@/lib/paths";
import { Provenance } from "./Provenance";
import { Chip, EmptyState, Loading, SectionHeader } from "./states";

const DEFAULT_SYMBOLS = (process.env.NEXT_PUBLIC_WATCHLIST ?? "SPY,QQQ")
  .split(",")
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);

type SortKey = "score" | "bias" | "vrp";

const EDGE_FADE = {
  WebkitMaskImage: "linear-gradient(90deg, transparent, #000 14px, #000 calc(100% - 14px), transparent)",
  maskImage: "linear-gradient(90deg, transparent, #000 14px, #000 calc(100% - 14px), transparent)",
} as const;

const biasColor = (s: number) => (s > 15 ? "text-call" : s < -15 ? "text-put" : "text-neutral-400");
const regimeChip = (r: string) =>
  r === "long"
    ? "border-call/30 bg-call/10 text-call"
    : r === "short"
      ? "border-put/30 bg-put/10 text-put"
      : "border-white/10 bg-white/[0.03] text-neutral-400";
const f2 = (n: number | null) => (n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 }));

function MiniBias({ score }: { score: number }) {
  const pct = (score + 100) / 2;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-16 rounded-full bg-gradient-to-r from-put/40 via-white/10 to-call/40">
        <span aria-hidden className="absolute left-1/2 top-1/2 h-2 w-px -translate-x-1/2 -translate-y-1/2 bg-white/25" />
        <span
          aria-hidden
          className="absolute top-1/2 h-2.5 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_6px_rgba(255,255,255,0.4)] transition-[left] duration-300"
          style={{ left: `calc(${pct}% - 1.5px)` }}
        />
      </div>
      <span className={`w-9 text-right font-mono text-xs tabular-nums ${biasColor(score)}`}>
        {score > 0 ? "+" : ""}
        {score}
      </span>
    </div>
  );
}

export function Scanner() {
  const [rows, setRows] = useState<ScanRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");

  const scan = useCallback(async () => {
    setLoading(true);
    const results = await Promise.all(
      DEFAULT_SYMBOLS.map(async (sym) => {
        try {
          const [ch, hi] = await Promise.all([loadChain(sym), loadHistory(sym).catch(() => ({ bars: [] as HistoryBar[] }))]);
          if (!ch.chain.length) return null;
          return { row: scanRow(sym, ch.chain, ch.spot, ("bars" in hi ? hi.bars : []) as HistoryBar[]), source: ch.source };
        } catch {
          return null;
        }
      }),
    );
    const ok = results.filter((r): r is { row: ScanRow; source: string } => r != null);
    setRows(ok.map((r) => r.row));
    setSource(ok[0]?.source ?? "");
    setLoading(false);
  }, []);

  useEffect(() => {
    scan();
  }, [scan]);

  useEffect(() => {
    const ms = Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60000) || 0;
    if (ms <= 0) return;
    const id = setInterval(scan, Math.max(60000, ms));
    return () => clearInterval(id);
  }, [scan]);

  const view = useMemo(() => {
    const val = (r: ScanRow) => (sortKey === "score" ? r.top?.score ?? 0 : sortKey === "vrp" ? r.vrp ?? 0 : Math.abs(r.biasScore));
    return [...rows].sort((a, b) => val(b) - val(a));
  }, [rows, sortKey]);

  const summary = useMemo(() => {
    const bull = rows.filter((r) => r.bias === "bullish").length;
    const bear = rows.filter((r) => r.bias === "bearish").length;
    const richest = rows.reduce<ScanRow | null>((p, r) => ((r.vrp ?? 0) > (p?.vrp ?? 0) ? r : p), null);
    return { bull, bear, richest };
  }, [rows]);

  const refreshing = loading && rows.length > 0;

  return (
    <div className="glass p-4">
      <Provenance source={source} feed="CBOE delayed ~15 min" count={rows.length} className="mb-3" />
      <SectionHeader
        eyebrow="Watchlist"
        title="Signal scanner"
        right={
          <div className="flex items-center gap-2">
            <div className="relative">
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                aria-label="Sort scanner rows"
                className="appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-2 pl-3 pr-8 text-xs text-neutral-200 outline-none transition hover:border-white/20 focus:border-accent/50"
              >
                <option value="score">Sort · conviction</option>
                <option value="bias">Sort · bias</option>
                <option value="vrp">Sort · VRP</option>
              </select>
              <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
                <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <button onClick={scan} className="btn text-xs">
              Refresh
            </button>
          </div>
        }
      />
      <p className="-mt-2 mb-3 text-xs text-neutral-500">
        Composite bias · dealer regime · VRP · key levels · top signal — across the watchlist.
      </p>

      {!loading && rows.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <Chip tone="call">{summary.bull} bullish</Chip>
          <Chip tone="put">{summary.bear} bearish</Chip>
          {summary.richest?.vrp != null && (
            <Chip>
              Richest VRP
              <span className="font-mono tabular-nums text-amber-300">
                {summary.richest.symbol} {summary.richest.vrp.toFixed(2)}×
              </span>
            </Chip>
          )}
        </div>
      )}

      {loading && rows.length === 0 ? (
        <Loading label="Loading scanner…" />
      ) : rows.length === 0 ? (
        <EmptyState label="No scan results." hint="No watchlist symbol returned a usable option chain." />
      ) : (
        <div className={`overflow-x-auto transition-opacity duration-300 ${refreshing ? "opacity-60" : ""}`} style={EDGE_FADE}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="!text-right">Spot</th>
                <th>Bias</th>
                <th>Regime</th>
                <th className="!text-right">VRP</th>
                <th className="!text-right">γ-flip</th>
                <th className="!text-right">Put / Call wall</th>
                <th>Top signal</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr key={r.symbol}>
                  <td>
                    <a className="font-semibold text-neutral-100 transition hover:text-accent-bright" href={withBase(`/ticker/${r.symbol}`)}>
                      {r.symbol}
                    </a>
                  </td>
                  <td className="text-right font-mono tabular-nums">{f2(r.spot)}</td>
                  <td>
                    <MiniBias score={r.biasScore} />
                  </td>
                  <td>
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] ${regimeChip(r.regime)}`}>
                      {r.regime === "long" ? "Long γ" : r.regime === "short" ? "Short γ" : "—"}
                    </span>
                  </td>
                  <td
                    className={`text-right font-mono tabular-nums ${
                      r.vrp == null ? "" : r.vrp >= 1.1 ? "text-amber-300" : r.vrp <= 0.95 ? "text-sky-300" : ""
                    }`}
                  >
                    {r.vrp == null ? "—" : `${r.vrp.toFixed(2)}×`}
                  </td>
                  <td className="text-right font-mono tabular-nums text-neutral-400">{r.flip == null ? "—" : f2(r.flip)}</td>
                  <td className="text-right font-mono tabular-nums text-neutral-400">
                    {r.putWall ?? "—"} / {r.callWall ?? "—"}
                  </td>
                  <td>
                    {r.top ? (
                      <a href={withBase(`/ticker/${r.symbol}`)} className="group inline-flex items-center gap-2">
                        <span
                          className={`inline-block w-8 rounded-md border py-0.5 text-center font-mono text-xs tabular-nums ${
                            r.top.score >= 70
                              ? "border-call/30 bg-call/10 text-call"
                              : r.top.score >= 50
                                ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                                : "border-white/10 bg-white/[0.03] text-neutral-400"
                          }`}
                        >
                          {r.top.score}
                        </span>
                        <span className="text-neutral-300 transition group-hover:text-neutral-100">{r.top.title}</span>
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
