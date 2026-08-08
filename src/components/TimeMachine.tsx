"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadDaySnapshot } from "@/lib/client-data";
import { fmtUsd } from "@/lib/flow/analytics";
import { dayStats, groupByDay } from "@/lib/flow/historyDays";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { readHistory } from "@/lib/gex-history";
import type { DaySnapshot } from "@/lib/intel/snapshot";
import { useChartFrame } from "./chartFrame";
import { EmptyState, Loading, SectionHeader, Stat } from "./states";

/**
 * Past-day view ("as of" a recorded date).
 *
 * Two independent records back this: the aggregate intraday series (spot / GEX / DEX / IV, recorded
 * around the clock) and a per-strike daily snapshot. Expired chains cannot be re-fetched from any free
 * feed, so a day only has per-strike detail if it was recorded live — days predating that recording show
 * the aggregate view and say so rather than inventing a profile.
 */

type Profile = "gex" | "dex" | "oi";

export function TimeMachine({ symbol, day, onLive }: { symbol: string; day: string; onLive: () => void }) {
  const [snap, setSnap] = useState<DaySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<Profile>("gex");
  const frame = useChartFrame(`${symbol} ${day}`);

  const series = useMemo(() => {
    const d = groupByDay(readHistory(symbol)).find((x) => x.key === day);
    return d?.samples ?? [];
  }, [symbol, day]);
  const stats = useMemo(() => (series.length ? dayStats(series) : null), [series]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadDaySnapshot(symbol, day)
      .then((s) => !cancelled && setSnap(s))
      .catch(() => !cancelled && setSnap(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [symbol, day]);

  const label = new Date(`${day}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  const intraday = useMemo(
    () =>
      series.map((s) => ({
        time: new Date(s.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        spot: s.spot,
        gex: s.gex,
      })),
    [series],
  );

  const profileData = useMemo(() => {
    if (!snap?.strikes?.length) return [];
    return snap.strikes.map((x) => ({
      strike: x.k,
      gex: x.g,
      dex: x.d,
      oi: x.co + x.po,
      callOi: x.co,
      putOi: x.po,
    }));
  }, [snap]);

  const P: Record<Profile, { label: string; key: "gex" | "dex" | "oi"; fmt: (v: number) => string; signed: boolean }> = {
    gex: { label: "Dealer GEX by strike", key: "gex", fmt: (v) => fmtUsd(v), signed: true },
    dex: { label: "Dealer DEX by strike", key: "dex", fmt: (v) => fmtUsd(v), signed: true },
    oi: { label: "Open interest by strike", key: "oi", fmt: (v) => Math.round(v).toLocaleString(), signed: false },
  };
  const p = P[profile];

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <SectionHeader
        eyebrow={`Time machine · ${symbol}`}
        title={label}
        right={
          <div className="flex items-center gap-2">
            <button onClick={onLive} className="rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-accent-bright transition hover:bg-accent/20">
              ← Back to live
            </button>
            {frame.controls}
          </div>
        }
      />

      {/* Recorded headline metrics for the day */}
      {stats ? (
        <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Spot close" value={stats.spotClose == null ? "—" : stats.spotClose.toLocaleString()} sub={stats.spotChangePct == null ? undefined : `${stats.spotChangePct >= 0 ? "+" : ""}${stats.spotChangePct.toFixed(2)}% on the day`} tone={stats.spotChangePct == null ? undefined : stats.spotChangePct >= 0 ? "call" : "put"} />
          <Stat label="Net GEX close" value={stats.gexClose == null ? "—" : fmtUsd(stats.gexClose)} tone={stats.gexClose == null ? undefined : stats.gexClose >= 0 ? "call" : "put"} sub={stats.gexClose == null ? undefined : stats.gexClose >= 0 ? "long γ · dampening" : "short γ · amplifying"} />
          <Stat label="GEX range" value={stats.gexMin == null || stats.gexMax == null ? "—" : `${fmtUsd(stats.gexMin)} … ${fmtUsd(stats.gexMax)}`} />
          <Stat label="Net DEX close" value={stats.dexClose == null ? "—" : fmtUsd(stats.dexClose)} sub={stats.dexClose == null ? "not recorded that day" : undefined} tone={stats.dexClose == null ? undefined : stats.dexClose >= 0 ? "call" : "put"} />
          <Stat label="ATM IV range" value={stats.ivMin == null || stats.ivMax == null ? "—" : `${(stats.ivMin * 100).toFixed(1)}–${(stats.ivMax * 100).toFixed(1)}%`} />
          <Stat label="γ-flip close" value={stats.flipClose == null ? "—" : `$${stats.flipClose.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
        </div>
      ) : (
        <EmptyState label={`No intraday record for ${label}.`} hint="The round-the-clock collector had no samples that day." />
      )}

      {/* Intraday spot vs GEX for the day */}
      {intraday.length > 1 && (
        <>
          <div className="lbl mb-1.5">Intraday · spot vs net GEX</div>
          <div className={`${frame.expanded ? "h-[38vh]" : "h-[240px]"} w-full`}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={intraday} margin={{ top: 6, right: 8, left: 4, bottom: 6 }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={40} />
                <YAxis yAxisId="spot" {...AXIS_PROPS} width={56} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toLocaleString()} />
                <YAxis yAxisId="gex" orientation="right" {...AXIS_PROPS} tick={{ fill: CHART.call, fontSize: 10, opacity: 0.8 }} width={56} domain={["auto", "auto"]} tickFormatter={(v) => fmtUsd(Number(v))} />
                <Tooltip {...TOOLTIP_PROPS} cursor={TOOLTIP_CURSOR_LINE} formatter={(v: number | string, n) => (n === "Net GEX" ? [fmtUsd(Number(v)), n] : [Number(v).toLocaleString(), n])} />
                <ReferenceLine yAxisId="gex" y={0} stroke="rgba(255,255,255,0.16)" />
                <Line yAxisId="spot" type="monotone" dataKey="spot" name="Spot" stroke="#a3a3a3" dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} />
                <Line yAxisId="gex" type="monotone" dataKey="gex" name="Net GEX" stroke={CHART.call} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {/* Per-strike profile recorded for that day */}
      <div className="mt-5 border-t border-white/[0.05] pt-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="lbl">Recorded positioning by strike</div>
          {snap && (
            <div className="flex items-center gap-1">
              {(Object.keys(P) as Profile[]).map((k) => (
                <button
                  key={k}
                  onClick={() => setProfile(k)}
                  aria-pressed={profile === k}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${profile === k ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
                >
                  {k === "gex" ? "GEX" : k === "dex" ? "DEX" : "OI"}
                </button>
              ))}
            </div>
          )}
        </div>

        {loading ? (
          <Loading label="Loading recorded snapshot…" />
        ) : !snap || !profileData.length ? (
          <EmptyState
            label="No per-strike snapshot for this day."
            hint="Per-strike recording started recently — expired chains can't be re-fetched from the feed, so only days captured live carry a strike profile. Days from here on will have one."
          />
        ) : (
          <>
            <div className={`${frame.expanded ? "h-[38vh]" : "h-[300px]"} w-full`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={profileData} margin={{ top: 6, right: 8, left: 4, bottom: 6 }}>
                  <CartesianGrid {...GRID_PROPS} />
                  <XAxis dataKey="strike" {...AXIS_PROPS} minTickGap={24} />
                  <YAxis {...AXIS_PROPS} width={60} tickFormatter={(v) => p.fmt(Number(v))} />
                  <Tooltip {...TOOLTIP_PROPS} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v: number | string) => [p.fmt(Number(v)), p.label]} labelFormatter={(l) => `Strike ${l}`} />
                  {p.signed && <ReferenceLine y={0} stroke="rgba(255,255,255,0.16)" />}
                  {snap.spot != null && <ReferenceLine x={profileData.reduce((a, b) => (Math.abs(b.strike - (snap.spot as number)) < Math.abs(a.strike - (snap.spot as number)) ? b : a)).strike} stroke="#fafafa" strokeDasharray="3 3" label={{ value: "spot", fill: "#fafafa", fontSize: 10, position: "top" }} />}
                  {snap.flip != null && <ReferenceLine x={profileData.reduce((a, b) => (Math.abs(b.strike - (snap.flip as number)) < Math.abs(a.strike - (snap.flip as number)) ? b : a)).strike} stroke="#a78bfa" strokeDasharray="4 2" label={{ value: "γ-flip", fill: "#a78bfa", fontSize: 10, position: "insideTopRight" }} />}
                  <Bar dataKey={p.key} name={p.label} isAnimationActive={false} radius={[2, 2, 0, 0]}>
                    {profileData.map((d) => (
                      <Cell key={d.strike} fill={p.signed ? ((d[p.key] as number) >= 0 ? CHART.call : CHART.put) : "#38bdf8"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-neutral-600">
              Snapshot taken {new Date(snap.t).toLocaleString()} · {snap.strikes.length} strikes · spot {snap.spot?.toLocaleString() ?? "—"}
              {snap.flip != null ? ` · γ-flip $${snap.flip.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : ""}. This is the recorded closing picture for the day, not a live chain. Educational — not advice.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
