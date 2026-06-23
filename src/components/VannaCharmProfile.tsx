"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { OptionContract } from "@/lib/barchart/types";
import {
  exposureProfile,
  filterByExpiration,
  flipFromProfile,
  fmtUsd,
  secondOrderExposure,
} from "@/lib/flow/analytics";
import { loadChain } from "@/lib/client-data";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";
type ProfMetric = "gex" | "vanna" | "charm";

const PROF_META: Record<ProfMetric, { label: string; color: string; unit: string }> = {
  gex: { label: "Net GEX", color: "#10b981", unit: "$/1%" },
  vanna: { label: "Vanna", color: "#a855f7", unit: "$/vol-pt" },
  charm: { label: "Charm", color: "#f59e0b", unit: "$/day" },
};

function windowAroundSpot<T extends { strike: number }>(rows: T[], spot: number | null, n = 31): T[] {
  if (spot == null || rows.length <= n) return rows;
  let idx = 0;
  let best = Infinity;
  rows.forEach((x, i) => {
    const d = Math.abs(x.strike - spot);
    if (d < best) {
      best = d;
      idx = i;
    }
  });
  const half = Math.floor(n / 2);
  return rows.slice(Math.max(0, idx - half), Math.max(0, idx - half) + n);
}

export function VannaCharmProfile({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [profMetric, setProfMetric] = useState<ProfMetric>("gex");

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

  const sub = useMemo(() => filterByExpiration(chain, exp), [chain, exp]);
  const so = useMemo(() => secondOrderExposure(sub, spot), [sub, spot]);

  const byStrike = useMemo(() => {
    const rows = windowAroundSpot(so.byStrike, spot).slice().sort((a, b) => b.strike - a.strike);
    return rows;
  }, [so.byStrike, spot]);

  const nearestStrike = useMemo(() => {
    if (spot == null || !byStrike.length) return null;
    return byStrike.reduce((p, c) => (Math.abs(c.strike - spot) < Math.abs(p - spot) ? c.strike : p), byStrike[0].strike);
  }, [byStrike, spot]);

  const profile = useMemo(() => exposureProfile(sub, spot), [sub, spot]);
  const profFlip = useMemo(() => flipFromProfile(profile), [profile]);
  const profData = useMemo(() => profile.map((p) => ({ spot: Math.round(p.spot * 100) / 100, val: p[profMetric] })), [profile, profMetric]);

  const height = Math.min(680, Math.max(360, byStrike.length * 20));
  const meta = PROF_META[profMetric];

  return (
    <div className="space-y-4">
      <div className="glass p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Vanna &amp; Charm by strike · {symbol}</h2>
          <span className="text-xs text-neutral-500">dealer 2nd-order exposure (calls +, puts −)</span>
        </div>
        {state === "loading" && <Loading label="Modeling greeks…" />}
        {state === "error" && <ErrorState message={error} />}
        {state === "empty" && <EmptyState label="No options data (needs greeks)." />}
        {state === "ok" && (
          <>
            <div className="grid gap-4 lg:grid-cols-2">
              <ByStrikeChart
                title="Vanna exposure"
                sub="$Δ / 1 vol-pt · positive = falling-IV tailwind"
                data={byStrike.map((x) => ({ strike: x.strike, v: x.vanna }))}
                nearestStrike={nearestStrike}
                height={height}
                pos="#a855f7"
                neg="#6b7280"
              />
              <ByStrikeChart
                title="Charm exposure"
                sub="$Δ / day · sign = decay drift direction"
                data={byStrike.map((x) => ({ strike: x.strike, v: x.charm }))}
                nearestStrike={nearestStrike}
                height={height}
                pos="#ef4444"
                neg="#10b981"
              />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Mini label="Net vanna" value={so.vanna == null ? "—" : `${fmtUsd(so.vanna)}/vol-pt`} tone={so.vanna == null ? "" : so.vanna >= 0 ? "text-emerald-400" : "text-red-400"} />
              <Mini label="Net charm" value={so.charm == null ? "—" : `${fmtUsd(so.charm)}/day`} tone={so.charm == null ? "" : so.charm >= 0 ? "text-red-400" : "text-emerald-400"} />
              <Mini label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
              <Mini label="Strikes shown" value={String(byStrike.length)} />
            </div>
          </>
        )}
      </div>

      {state === "ok" && profData.length > 0 && (
        <div className="glass p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Exposure across spot · {symbol}</h2>
            <div className="flex items-center gap-1 text-xs">
              {(Object.keys(PROF_META) as ProfMetric[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setProfMetric(m)}
                  className={`rounded-md px-2 py-1 transition ${
                    profMetric === m ? "bg-white/10 text-neutral-100" : "text-neutral-400 hover:bg-white/5"
                  }`}
                >
                  {PROF_META[m].label}
                </button>
              ))}
            </div>
          </div>
          <p className="mb-2 text-xs text-neutral-500">
            Re-priced (Black-Scholes, sticky-strike) as if spot moved — where {meta.label.toLowerCase()} crosses zero is the
            regime flip. {profMetric === "gex" && profFlip != null ? `Modeled γ-flip ≈ ${profFlip.toFixed(2)}.` : ""}
          </p>
          <div style={{ height: 300 }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={profData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
                <XAxis dataKey="spot" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
                <YAxis tickFormatter={(v) => fmtUsd(Number(v))} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" width={64} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string) => [fmtUsd(Number(v)), `${meta.label} (${meta.unit})`]}
                  labelFormatter={(l) => `spot ${l}`}
                />
                <ReferenceLine y={0} stroke="#525252" />
                {spot != null && (
                  <ReferenceLine x={spot} stroke="#e5e5e5" strokeDasharray="4 4" label={{ value: "spot", position: "top", fill: "#e5e5e5", fontSize: 11 }} />
                )}
                {profMetric === "gex" && profFlip != null && (
                  <ReferenceLine x={Math.round(profFlip * 100) / 100} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: "flip", position: "top", fill: "#f59e0b", fontSize: 11 }} />
                )}
                <Line type="monotone" dataKey="val" stroke={meta.color} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

function ByStrikeChart({
  title,
  sub,
  data,
  nearestStrike,
  height,
  pos,
  neg,
}: {
  title: string;
  sub: string;
  data: { strike: number; v: number }[];
  nearestStrike: number | null;
  height: number;
  pos: string;
  neg: string;
}) {
  return (
    <div>
      <div className="mb-1 text-sm font-medium text-neutral-200">{title}</div>
      <div className="mb-2 text-[11px] text-neutral-500">{sub}</div>
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 28, left: 4, bottom: 4 }}>
            <XAxis type="number" tickFormatter={(v) => fmtUsd(Number(v))} tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" />
            <YAxis type="category" dataKey="strike" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={52} interval={0} />
            <Tooltip
              contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
              formatter={(v: number | string) => [fmtUsd(Number(v)), title]}
              labelFormatter={(l) => `strike ${l}`}
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
            />
            <ReferenceLine x={0} stroke="#525252" />
            {nearestStrike != null && (
              <ReferenceLine y={nearestStrike} stroke="#e5e5e5" strokeDasharray="4 4" label={{ value: "S", position: "right", fill: "#e5e5e5", fontSize: 11 }} />
            )}
            <Bar dataKey="v" radius={[0, 3, 3, 0]} isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.strike} fill={d.v >= 0 ? pos : neg} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Mini({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-base ${tone || "text-neutral-100"}`}>{value}</div>
    </div>
  );
}
