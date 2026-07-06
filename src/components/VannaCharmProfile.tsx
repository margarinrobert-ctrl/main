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
import { AXIS_PROPS, CHART, CHART_TICK, TOOLTIP_CURSOR, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS, refLabel } from "@/lib/chartTheme";
import { EmptyState, ErrorState, Loading, SectionHeader, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";
type ProfMetric = "gex" | "vanna" | "charm";

const PROF_META: Record<ProfMetric, { label: string; color: string; unit: string }> = {
  gex: { label: "Net GEX", color: CHART.call, unit: "$/1%" },
  vanna: { label: "Vanna", color: CHART.cyan, unit: "$/vol-pt" },
  charm: { label: "Charm", color: CHART.amber, unit: "$/day" },
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
      <div className="glass glass-hover fade-up p-4 sm:p-5">
        <SectionHeader eyebrow="Vanna &amp; charm" title={symbol} right={<span className="lbl">Dealer 2nd-order exposure by strike</span>} />
        {state === "loading" && <Loading label="Loading second-order greeks…" />}
        {state === "error" && <ErrorState message={error} />}
        {state === "empty" && <EmptyState label="Greeks unavailable for this chain." />}
        {state === "ok" && (
          <>
            <div className="grid gap-4 lg:grid-cols-2">
              <ByStrikeChart
                title="Vanna exposure"
                sub="$Δ per 1 vol-pt · positive: IV decline adds dealer buying"
                data={byStrike.map((x) => ({ strike: x.strike, v: x.vanna }))}
                nearestStrike={nearestStrike}
                height={height}
                pos={CHART.cyan}
                neg="rgba(255,255,255,0.28)"
              />
              <ByStrikeChart
                title="Charm exposure"
                sub="$Δ per day · positive: decay flow sells into the close"
                data={byStrike.map((x) => ({ strike: x.strike, v: x.charm }))}
                nearestStrike={nearestStrike}
                height={height}
                pos={CHART.put}
                neg={CHART.call}
              />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <Stat label="Net vanna" value={so.vanna == null ? "—" : `${fmtUsd(so.vanna)}/vol-pt`} tone={so.vanna == null ? undefined : so.vanna >= 0 ? "call" : "put"} />
              <Stat label="Net charm" value={so.charm == null ? "—" : `${fmtUsd(so.charm)}/day`} tone={so.charm == null ? undefined : so.charm >= 0 ? "put" : "call"} sub="inverted scale" />
              <Stat label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
              <Stat label="Strikes shown" value={String(byStrike.length)} />
            </div>
          </>
        )}
      </div>

      {state === "ok" && profData.length > 0 && (
        <div className="glass glass-hover fade-up p-4 sm:p-5">
          <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
            <div>
              <div className="lbl mb-1">Exposure across spot</div>
              <h2 className="display text-base text-neutral-50">{symbol}</h2>
            </div>
            <div className="flex items-center gap-1">
              {(Object.keys(PROF_META) as ProfMetric[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setProfMetric(m)}
                  aria-pressed={profMetric === m}
                  className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                    profMetric === m ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
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
              <LineChart data={profData} margin={{ top: 8, right: 16, left: 4, bottom: 8 }}>
                <XAxis dataKey="spot" type="number" domain={["dataMin", "dataMax"]} {...AXIS_PROPS} />
                <YAxis tickFormatter={(v) => fmtUsd(Number(v))} {...AXIS_PROPS} width={60} />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  cursor={TOOLTIP_CURSOR_LINE}
                  formatter={(v: number | string) => [fmtUsd(Number(v)), `${meta.label} (${meta.unit})`]}
                  labelFormatter={(l) => `Spot ${l}`}
                />
                <ReferenceLine y={0} stroke="rgba(255,255,255,0.16)" />
                {spot != null && (
                  <ReferenceLine x={spot} stroke={CHART.spot} strokeDasharray="4 4" label={refLabel("Spot", CHART.spot, "insideTopRight")} />
                )}
                {profMetric === "gex" && profFlip != null && (
                  <ReferenceLine x={Math.round(profFlip * 100) / 100} stroke={CHART.violet} strokeDasharray="4 4" label={refLabel("Flip", CHART.violet, "insideTopLeft")} />
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
      <div className="mb-1 text-sm font-medium text-neutral-100">{title}</div>
      <div className="mb-2 text-[11px] text-neutral-500">{sub}</div>
      <div style={{ height: Math.min(height, 460) }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 28, left: 4, bottom: 4 }}>
            <XAxis type="number" tickFormatter={(v) => fmtUsd(Number(v))} {...AXIS_PROPS} />
            <YAxis type="category" dataKey="strike" {...AXIS_PROPS} tick={CHART_TICK} width={48} interval={0} />
            <Tooltip
              {...TOOLTIP_PROPS}
              formatter={(v: number | string) => [fmtUsd(Number(v)), title]}
              labelFormatter={(l) => `Strike ${l}`}
              cursor={TOOLTIP_CURSOR}
            />
            <ReferenceLine x={0} stroke="rgba(255,255,255,0.16)" />
            {nearestStrike != null && (
              <ReferenceLine y={nearestStrike} stroke={CHART.spot} strokeDasharray="4 4" label={refLabel("Spot", CHART.spot, "insideTopRight")} />
            )}
            <Bar dataKey="v" isAnimationActive={false} shape={(props: unknown) => <SignedBar {...(props as Record<string, unknown>)} pos={pos} neg={neg} />} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        {[
          { c: pos, l: "Positive" },
          { c: neg, l: "Negative" },
        ].map((it) => (
          <span key={it.l} className="flex items-center gap-1.5 text-[10px] text-neutral-600">
            <span className="h-2 w-2 rounded-sm" style={{ background: it.c }} />
            {it.l}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Horizontal signed bar: rounds the outward edge (right for positive, left for negative). */
function SignedBar(props: Record<string, unknown> & { pos?: string; neg?: string }) {
  const { x, y, width, height, pos, neg } = props as { x: number; y: number; width: number; height: number; pos: string; neg: string };
  if (!Number.isFinite(width) || width === 0) return <g />;
  const positive = width >= 0;
  const rx = 3;
  const w = Math.abs(width);
  const rectX = positive ? x : x + width;
  const r = Math.min(rx, w);
  const path = positive
    ? `M${rectX},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${height - 2 * r} a${r},${r} 0 0 1 -${r},${r} h-${w - r} z`
    : `M${rectX + r},${y} h${w - r} v${height} h-${w - r} a${r},${r} 0 0 1 -${r},-${r} v-${height - 2 * r} a${r},${r} 0 0 1 ${r},-${r} z`;
  return <path d={path} fill={positive ? pos : neg} />;
}
