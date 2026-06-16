"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { HistoryBar } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { scanRow, type ScanRow } from "@/lib/flow/signals";
import { withBase } from "@/lib/paths";
import { Loading } from "./states";

const DEFAULT_SYMBOLS = (process.env.NEXT_PUBLIC_WATCHLIST ?? "SPY,QQQ,ES,NQ,AAPL,NVDA,TSLA")
  .split(",")
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);

type SortKey = "score" | "bias" | "vrp";

const biasColor = (s: number) => (s > 15 ? "text-emerald-300" : s < -15 ? "text-red-300" : "text-sky-300");
const regimeChip = (r: string) =>
  r === "long" ? "bg-emerald-500/10 text-emerald-300" : r === "short" ? "bg-red-500/10 text-red-300" : "bg-neutral-500/10 text-neutral-300";
const f2 = (n: number | null) => (n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 }));

function MiniBias({ score }: { score: number }) {
  const pct = (score + 100) / 2;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-16 rounded-full bg-gradient-to-r from-red-500/40 via-neutral-600/40 to-emerald-500/40">
        <div className="absolute top-1/2 h-2.5 w-1 -translate-y-1/2 rounded bg-white" style={{ left: `calc(${pct}% - 2px)` }} />
      </div>
      <span className={`w-8 font-mono text-xs ${biasColor(score)}`}>
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

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Signal Scanner</h2>
          <p className="text-xs text-neutral-500">
            composite bias · dealer regime · VRP · key levels · top trade — across the watchlist
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {!loading && rows.length > 0 && (
            <span className="hidden text-neutral-400 sm:inline">
              <span className="text-emerald-300">{summary.bull} bull</span> · <span className="text-red-300">{summary.bear} bear</span>
              {summary.richest?.vrp != null && (
                <>
                  {" "}
                  · richest VRP <span className="text-amber-300">{summary.richest.symbol} {summary.richest.vrp.toFixed(2)}×</span>
                </>
              )}
            </span>
          )}
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded border border-white/10 bg-neutral-900 px-2 py-1 text-neutral-200 outline-none"
          >
            <option value="score">sort: conviction</option>
            <option value="bias">sort: bias</option>
            <option value="vrp">sort: VRP</option>
          </select>
          <button onClick={scan} className="rounded bg-white/5 px-3 py-1 text-neutral-200 hover:bg-white/10">
            Refresh
          </button>
          {source && <span className="text-neutral-500">src: {source}</span>}
        </div>
      </div>

      {loading && rows.length === 0 ? (
        <Loading label="Scanning the watchlist…" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="py-2 pr-3">Ticker</th>
                <th className="pr-3 text-right">Spot</th>
                <th className="pr-3">Bias</th>
                <th className="pr-3">Regime</th>
                <th className="pr-3 text-right">VRP</th>
                <th className="pr-3 text-right">γ-flip</th>
                <th className="pr-3 text-right">Put / Call wall</th>
                <th className="pr-3">Top signal</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr key={r.symbol} className="border-b border-white/5 transition hover:bg-white/[0.03]">
                  <td className="py-2 pr-3">
                    <a className="font-semibold text-emerald-400 hover:underline" href={withBase(`/ticker/${r.symbol}`)}>
                      {r.symbol}
                    </a>
                  </td>
                  <td className="pr-3 text-right font-mono">{f2(r.spot)}</td>
                  <td className="pr-3">
                    <MiniBias score={r.biasScore} />
                  </td>
                  <td className="pr-3">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${regimeChip(r.regime)}`}>
                      {r.regime === "long" ? "Long γ" : r.regime === "short" ? "Short γ" : "—"}
                    </span>
                  </td>
                  <td className={`pr-3 text-right font-mono ${r.vrp == null ? "" : r.vrp >= 1.1 ? "text-amber-300" : r.vrp <= 0.95 ? "text-sky-300" : ""}`}>
                    {r.vrp == null ? "—" : `${r.vrp.toFixed(2)}×`}
                  </td>
                  <td className="pr-3 text-right font-mono text-neutral-400">{r.flip == null ? "—" : f2(r.flip)}</td>
                  <td className="pr-3 text-right font-mono text-neutral-400">
                    {r.putWall ?? "—"} / {r.callWall ?? "—"}
                  </td>
                  <td className="pr-3">
                    {r.top ? (
                      <a href={withBase(`/ticker/${r.symbol}`)} className="group inline-flex items-center gap-2">
                        <span
                          className={`inline-block w-7 rounded text-center font-mono text-xs ${
                            r.top.score >= 70 ? "bg-emerald-900 text-emerald-200" : r.top.score >= 50 ? "bg-amber-900 text-amber-200" : "bg-neutral-800 text-neutral-300"
                          }`}
                        >
                          {r.top.score}
                        </span>
                        <span className="text-neutral-300 group-hover:text-neutral-100">{r.top.title}</span>
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
