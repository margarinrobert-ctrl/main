"use client";

import { type ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import { loadFlow } from "@/lib/client-data";
import { withBase } from "@/lib/paths";
import { Provenance } from "./Provenance";
import { Chip, EmptyState, ErrorState, Loading } from "./states";

interface Row {
  underlying: string;
  symbol: string;
  type: "call" | "put";
  strike: number;
  expiration: string;
  dte: number | null;
  volume: number | null;
  openInterest: number | null;
  impliedVolatility: number | null;
  score: number;
  flags: string[];
  signals: { voir: number | null; notional: number | null; mid: number | null };
}

type ViewState = "loading" | "error" | "empty" | "ok";
type SortKey = "score" | "volume" | "openInterest" | "notional" | "voir";
type Side = "all" | "call" | "put";

interface ServerParams {
  minVolume: string;
  minOpenInterest: string;
  minDTE: string;
  maxDTE: string;
  minVoir: string;
}

const DEFAULT_PARAMS: ServerParams = { minVolume: "100", minOpenInterest: "50", minDTE: "", maxDTE: "", minVoir: "" };

/** Shared control recipe — inputs & selects read as one instrument. */
const CTRL =
  "rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2 font-mono text-sm tabular-nums text-neutral-100 outline-none transition focus:border-accent/50";

const EDGE_FADE = {
  WebkitMaskImage: "linear-gradient(90deg, transparent, #000 14px, #000 calc(100% - 14px), transparent)",
  maskImage: "linear-gradient(90deg, transparent, #000 14px, #000 calc(100% - 14px), transparent)",
} as const;

/** Abbreviated dollar notional — $1.24M instead of $1,240,000. */
function abbrevUsd(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${Math.round(n)}`;
}

export function FlowTable() {
  const [rows, setRows] = useState<Row[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [serverParams, setServerParams] = useState<ServerParams>(DEFAULT_PARAMS);
  const [minScore, setMinScore] = useState(0);
  const [side, setSide] = useState<Side>("all");
  const [sortKey, setSortKey] = useState<SortKey>("score");

  const load = useCallback(async () => {
    setState("loading");
    try {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(serverParams)) if (v !== "") qs.set(k, v);
      const { rows, source } = await loadFlow(qs.toString());
      setSource(source);
      setRows(rows as Row[]);
      setState(rows.length ? "ok" : "empty");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
  }, [serverParams]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const ms = Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60000) || 0;
    if (ms <= 0) return;
    const id = setInterval(() => load(), ms);
    return () => clearInterval(id);
  }, [load]);

  const setParam = (k: keyof ServerParams) => (e: ChangeEvent<HTMLInputElement>) =>
    setServerParams((p) => ({ ...p, [k]: e.target.value }));

  const view = useMemo(() => {
    const filtered = rows.filter((x) => x.score >= minScore && (side === "all" || x.type === side));
    const val = (x: Row): number => {
      switch (sortKey) {
        case "volume":
          return x.volume ?? 0;
        case "openInterest":
          return x.openInterest ?? 0;
        case "notional":
          return x.signals.notional ?? 0;
        case "voir":
          return x.signals.voir ?? 0;
        default:
          return x.score;
      }
    };
    return [...filtered].sort((a, b) => val(b) - val(a));
  }, [rows, minScore, side, sortKey]);

  const exportCsv = () => {
    const head = ["score", "ticker", "type", "strike", "expiration", "dte", "volume", "openInterest", "volOI", "iv", "notional", "flags"];
    const lines = view.map((r) =>
      [
        r.score,
        r.underlying,
        r.type,
        r.strike,
        r.expiration,
        r.dte ?? "",
        r.volume ?? "",
        r.openInterest ?? "",
        r.signals.voir != null ? r.signals.voir.toFixed(2) : "",
        r.impliedVolatility ?? "",
        r.signals.notional != null ? Math.round(r.signals.notional) : "",
        r.flags.join("|"),
      ].join(","),
    );
    const csv = [head.join(","), ...lines].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `flow-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /* Stale-while-refresh: keep the last tape rendered, dimmed, while new rows load. */
  const refreshing = state === "loading" && rows.length > 0;

  return (
    <div>
      <Provenance source={source} feed="options flow" count={rows.length} className="mb-3" />
      <div className="mb-3 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3.5">
        <div className="lbl mb-2.5">Screener filters</div>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <NumInput label="Min volume" value={serverParams.minVolume} onChange={setParam("minVolume")} />
          <NumInput label="Min OI" value={serverParams.minOpenInterest} onChange={setParam("minOpenInterest")} />
          <NumInput label="DTE ≥" value={serverParams.minDTE} onChange={setParam("minDTE")} />
          <NumInput label="DTE ≤" value={serverParams.maxDTE} onChange={setParam("maxDTE")} />
          <NumInput label="Min vol/OI" step="0.1" value={serverParams.minVoir} onChange={setParam("minVoir")} />
          <button onClick={load} className="btn btn-primary text-xs">
            Apply
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 text-sm">
        <span className="lbl w-full">View</span>
        <label className="flex flex-col gap-1.5">
          <span className="lbl">Min score</span>
          <input
            type="number"
            value={minScore}
            min={0}
            max={100}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className={`w-24 ${CTRL}`}
          />
        </label>
        <SelectField label="Side" value={side} onChange={(v) => setSide(v as Side)}>
          <option value="all">All</option>
          <option value="call">Calls</option>
          <option value="put">Puts</option>
        </SelectField>
        <SelectField label="Sort by" value={sortKey} onChange={(v) => setSortKey(v as SortKey)}>
          <option value="score">Score</option>
          <option value="volume">Volume</option>
          <option value="openInterest">Open interest</option>
          <option value="notional">Notional</option>
          <option value="voir">Vol/OI</option>
        </SelectField>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={exportCsv} className="btn text-xs">
            Export CSV
          </button>
          <button onClick={load} className="btn text-xs">
            Refresh
          </button>
        </div>
      </div>

      {state === "loading" && rows.length === 0 && <Loading label="Loading flow…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && (
        <EmptyState label="No unusual activity matched your filters." hint="Loosen the volume, open-interest or DTE gates to widen the screen." />
      )}
      {(state === "ok" || refreshing) && rows.length > 0 && (
        <>
          {refreshing && <div className="skeleton mb-2 h-1 w-full" aria-hidden />}
          {view.length === 0 ? (
            <EmptyState label="No rows match the current view." hint="Lower the min score or widen the side filter." />
          ) : (
            <div className={`overflow-x-auto transition-opacity duration-300 ${refreshing ? "opacity-60" : ""}`} style={EDGE_FADE}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Score</th>
                    <th>Ticker</th>
                    <th>Side</th>
                    <th className="!text-right">Strike</th>
                    <th>Exp</th>
                    <th className="!text-right">DTE</th>
                    <th className="!text-right">Vol</th>
                    <th className="!text-right">OI</th>
                    <th className="!text-right">Vol/OI</th>
                    <th className="!text-right">IV</th>
                    <th className="!text-right">Notional</th>
                    <th>Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {view.map((r) => (
                    <tr key={r.symbol}>
                      <td>
                        <ScoreBadge score={r.score} />
                      </td>
                      <td>
                        <a
                          className="font-semibold text-neutral-100 transition hover:text-accent-bright"
                          href={withBase(`/ticker/${r.underlying}`)}
                        >
                          {r.underlying}
                        </a>
                      </td>
                      <td>
                        <Chip tone={r.type}>{r.type === "call" ? "Call" : "Put"}</Chip>
                      </td>
                      <td className="text-right font-mono tabular-nums">{r.strike}</td>
                      <td className="font-mono tabular-nums text-neutral-400">{r.expiration}</td>
                      <td className="text-right font-mono tabular-nums">{r.dte ?? "—"}</td>
                      <td className="text-right font-mono tabular-nums">{r.volume?.toLocaleString() ?? "—"}</td>
                      <td className="text-right font-mono tabular-nums">{r.openInterest?.toLocaleString() ?? "—"}</td>
                      <td className="text-right font-mono tabular-nums">
                        {r.signals.voir != null ? r.signals.voir.toFixed(2) : "—"}
                      </td>
                      <td className="text-right font-mono tabular-nums">
                        {r.impliedVolatility != null ? r.impliedVolatility.toFixed(2) : "—"}
                      </td>
                      <td className="text-right font-mono tabular-nums">
                        {r.signals.notional != null ? abbrevUsd(r.signals.notional) : "—"}
                      </td>
                      <td>
                        <div className="flex flex-wrap gap-1">
                          {r.flags.map((f) => (
                            <Chip key={f}>{f}</Chip>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function NumInput({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  step?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="lbl">{label}</span>
      <input type="number" value={value} step={step} onChange={onChange} className={`w-24 ${CTRL}`} />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="lbl">{label}</span>
      <div className="relative">
        <select value={value} onChange={(e) => onChange(e.target.value)} className={`appearance-none pr-8 ${CTRL}`}>
          {children}
        </select>
        <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </label>
  );
}

/** Unusualness heat 0–100 — hotter (redder) = more anomalous flow. */
function ScoreBadge({ score }: { score: number }) {
  const cls =
    score >= 70
      ? "border-put/30 bg-put/10 text-put"
      : score >= 40
        ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
        : "border-white/10 bg-white/[0.03] text-neutral-400";
  return (
    <span
      title="Unusualness heat, 0–100 — weighted vol/OI, volume vs. average, dollar notional and short-DTE/OTM convexity. Hotter reads more anomalous."
      className={`inline-block w-9 rounded-md border py-0.5 text-center font-mono text-xs tabular-nums ${cls}`}
    >
      {score}
    </span>
  );
}
