"use client";

import { type ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, Loading } from "./states";

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
      const res = await fetch(`/api/barchart/screener?${qs.toString()}`, { cache: "no-store" });
      const json = await res.json();
      if (!res.ok) {
        setError(json?.error ?? "Request failed");
        setState("error");
        return;
      }
      setSource(json.source ?? "");
      const data: Row[] = json.rows ?? [];
      setRows(data);
      setState(data.length ? "ok" : "empty");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
  }, [serverParams]);

  useEffect(() => {
    load();
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

  return (
    <div>
      <div className="mb-3 rounded border border-neutral-800 p-3">
        <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
          Screener — maps to getOptionsScreener params
        </div>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <NumInput label="min volume" value={serverParams.minVolume} onChange={setParam("minVolume")} />
          <NumInput label="min OI" value={serverParams.minOpenInterest} onChange={setParam("minOpenInterest")} />
          <NumInput label="DTE ≥" value={serverParams.minDTE} onChange={setParam("minDTE")} />
          <NumInput label="DTE ≤" value={serverParams.maxDTE} onChange={setParam("maxDTE")} />
          <NumInput label="min vol/OI" step="0.1" value={serverParams.minVoir} onChange={setParam("minVoir")} />
          <button onClick={load} className="rounded bg-emerald-700 px-3 py-1 hover:bg-emerald-600">
            Apply
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 text-sm">
        <span className="w-full text-xs uppercase tracking-wide text-neutral-500">View</span>
        <label className="flex flex-col gap-1">
          <span className="text-neutral-400">min score</span>
          <input
            type="number"
            value={minScore}
            min={0}
            max={100}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="w-24 rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-neutral-400">side</span>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as Side)}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            <option value="all">all</option>
            <option value="call">calls</option>
            <option value="put">puts</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-neutral-400">sort by</span>
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            <option value="score">score</option>
            <option value="volume">volume</option>
            <option value="openInterest">open interest</option>
            <option value="notional">notional</option>
            <option value="voir">vol/OI</option>
          </select>
        </label>
        <button onClick={load} className="ml-auto rounded bg-neutral-800 px-3 py-1 hover:bg-neutral-700">
          Refresh
        </button>
        {source && <span className="self-center text-xs text-neutral-500">src: {source}</span>}
      </div>

      {state === "loading" && <Loading label="Loading flow…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No unusual activity matched your filters." />}
      {state === "ok" && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-neutral-800 text-left text-neutral-400">
              <tr>
                <th className="py-2 pr-3">Score</th>
                <th className="pr-3">Ticker</th>
                <th className="pr-3">C/P</th>
                <th className="pr-3 text-right">Strike</th>
                <th className="pr-3">Exp</th>
                <th className="pr-3 text-right">DTE</th>
                <th className="pr-3 text-right">Vol</th>
                <th className="pr-3 text-right">OI</th>
                <th className="pr-3 text-right">Vol/OI</th>
                <th className="pr-3 text-right">IV</th>
                <th className="pr-3 text-right">Notional</th>
                <th className="pr-3">Flags</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr key={r.symbol} className="border-b border-neutral-900 hover:bg-neutral-900/50">
                  <td className="py-2 pr-3">
                    <ScoreBadge score={r.score} />
                  </td>
                  <td className="pr-3">
                    <a className="text-emerald-400 hover:underline" href={`/ticker/${r.underlying}`}>
                      {r.underlying}
                    </a>
                  </td>
                  <td className={`pr-3 ${r.type === "call" ? "text-emerald-400" : "text-red-400"}`}>{r.type}</td>
                  <td className="pr-3 text-right">{r.strike}</td>
                  <td className="pr-3">{r.expiration}</td>
                  <td className="pr-3 text-right">{r.dte ?? "—"}</td>
                  <td className="pr-3 text-right">{r.volume?.toLocaleString() ?? "—"}</td>
                  <td className="pr-3 text-right">{r.openInterest?.toLocaleString() ?? "—"}</td>
                  <td className="pr-3 text-right">{r.signals.voir != null ? r.signals.voir.toFixed(2) : "—"}</td>
                  <td className="pr-3 text-right">{r.impliedVolatility != null ? r.impliedVolatility.toFixed(2) : "—"}</td>
                  <td className="pr-3 text-right">
                    {r.signals.notional != null ? "$" + Math.round(r.signals.notional).toLocaleString() : "—"}
                  </td>
                  <td className="pr-3">
                    <div className="flex flex-wrap gap-1">
                      {r.flags.map((f) => (
                        <span key={f} className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px]">
                          {f}
                        </span>
                      ))}
                    </div>
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
    <label className="flex flex-col gap-1">
      <span className="text-neutral-400">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={onChange}
        className="w-24 rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
      />
    </label>
  );
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? "bg-red-900 text-red-200" : score >= 40 ? "bg-amber-900 text-amber-200" : "bg-neutral-800 text-neutral-300";
  return <span className={`inline-block w-9 rounded text-center font-mono ${color}`}>{score}</span>;
}
