"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS, refLabel } from "@/lib/chartTheme";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

// near → far colour ramp (emerald → cyan → blue → indigo → violet → purple)
const RAMP = ["#34d399", "#22d3ee", "#38bdf8", "#818cf8", "#a78bfa", "#c084fc"];
const WINDOW = 18; // ±% moneyness shown

interface Smile {
  exp: string;
  dte: number | null;
  color: string;
  points: { m: number; iv: number }[];
}

export function VolSmile({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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

  const { smiles, atmIv, skew } = useMemo(() => {
    if (!spot || !chain.length) return { smiles: [] as Smile[], atmIv: null as number | null, skew: null as number | null };
    const exps = [...new Map(chain.map((c) => [c.expiration, c.dte])).entries()]
      .filter(([, d]) => (d ?? -1) >= 0)
      .sort((a, b) => (a[1] ?? 9e9) - (b[1] ?? 9e9));
    const chosen = (exp !== "ALL" && exps.some(([e]) => e === exp) ? [exps.find(([e]) => e === exp)!, ...exps.filter(([e]) => e !== exp)] : exps).slice(0, 6);

    const smiles: Smile[] = chosen.map(([e, dte], idx) => {
      const m = new Map<number, { c?: number; p?: number }>();
      for (const o of chain) {
        if (o.expiration !== e || o.impliedVolatility == null || o.impliedVolatility <= 0) continue;
        const mm = ((o.strike - spot) / spot) * 100;
        if (Math.abs(mm) > WINDOW) continue;
        const cur = m.get(o.strike) ?? {};
        if (o.type === "call") cur.c = o.impliedVolatility * 100;
        else cur.p = o.impliedVolatility * 100;
        m.set(o.strike, cur);
      }
      // OTM-preferred IV → the clean smile: puts below spot, calls above, blend at the money
      const points = [...m.entries()]
        .map(([strike, v]) => {
          const mm = ((strike - spot) / spot) * 100;
          const iv = mm < -0.5 ? v.p ?? v.c : mm > 0.5 ? v.c ?? v.p : v.c != null && v.p != null ? (v.c + v.p) / 2 : v.c ?? v.p;
          return iv == null ? null : { m: Math.round(mm * 100) / 100, iv };
        })
        .filter((x): x is { m: number; iv: number } => x != null)
        .sort((a, b) => a.m - b.m);
      return { exp: e, dte, color: RAMP[idx % RAMP.length], points };
    }).filter((s) => s.points.length >= 3);

    const front = smiles[0];
    const at = (pts: { m: number; iv: number }[], target: number) =>
      pts.length ? pts.reduce((p, c) => (Math.abs(c.m - target) < Math.abs(p.m - target) ? c : p)).iv : null;
    const atmIv = front ? at(front.points, 0) : null;
    const put10 = front ? at(front.points, -10) : null;
    const call10 = front ? at(front.points, 10) : null;
    const skew = put10 != null && call10 != null ? put10 - call10 : null; // >0 = put skew (smirk)
    return { smiles, atmIv, skew };
  }, [chain, spot, exp]);

  const front = smiles[0];

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="lbl mb-1">Volatility smile</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          {atmIv != null && (
            <span className="inline-flex items-center rounded-full border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 tabular-nums text-sky-300">
              ATM IV {atmIv.toFixed(1)}%
            </span>
          )}
          {skew != null && (
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-1 tabular-nums ${skew >= 0 ? "border-put/30 bg-put/10 text-put" : "border-call/30 bg-call/10 text-call"}`}
              title="IV(−10%) − IV(+10%): positive = downside put skew (smirk)"
            >
              skew {skew >= 0 ? "+" : ""}{skew.toFixed(1)}pt {skew >= 0 ? "(put)" : "(call)"}
            </span>
          )}
        </div>
      </div>
      {state === "loading" && <Loading label="Loading volatility smile…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No implied-volatility data for a smile." />}
      {state === "ok" && smiles.length === 0 && <EmptyState label="Not enough IV points to draw a smile." />}
      {state === "ok" && smiles.length > 0 && (
        <>
          <div className="h-[360px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart margin={{ top: 10, right: 16, left: 4, bottom: 6 }}>
                <defs>
                  <linearGradient id="smileFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={front?.color ?? "#34d399"} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={front?.color ?? "#34d399"} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis
                  type="number"
                  dataKey="m"
                  domain={[-WINDOW, WINDOW]}
                  tickFormatter={(v) => `${v > 0 ? "+" : ""}${v}%`}
                  {...AXIS_PROPS}
                  allowDuplicatedCategory={false}
                />
                <YAxis tickFormatter={(v) => `${v}%`} {...AXIS_PROPS} width={44} domain={["auto", "auto"]} />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  cursor={TOOLTIP_CURSOR_LINE}
                  formatter={(v: number | string, n) => [`${Number(v).toFixed(1)}%`, n]}
                  labelFormatter={(l) => `${Number(l) > 0 ? "+" : ""}${l}% from spot`}
                />
                <ReferenceLine x={0} stroke={CHART.amber} strokeDasharray="4 4" label={refLabel("ATM", CHART.amber, "insideTopRight")} />
                {front && <Area data={front.points} dataKey="iv" stroke="none" fill="url(#smileFill)" isAnimationActive={false} />}
                {smiles.map((s, i) => (
                  <Line
                    key={s.exp}
                    data={s.points}
                    dataKey="iv"
                    name={s.dte != null ? `${s.dte}d` : s.exp.slice(5)}
                    stroke={s.color}
                    strokeWidth={i === 0 ? 2.6 : 1.4}
                    strokeOpacity={i === 0 ? 1 : 0.75}
                    dot={false}
                    type="monotone"
                    isAnimationActive={false}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-white/[0.05] pt-3">
            {smiles.map((s) => (
              <span key={s.exp} className="inline-flex items-center gap-1.5 text-[11px] text-neutral-500">
                <span className="inline-block h-2 w-3 rounded-sm" style={{ background: s.color }} />
                {s.dte != null ? `${s.dte}d` : s.exp}
              </span>
            ))}
            <span className="text-[11px] text-neutral-600">· x = % from spot · OTM-side IV</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-neutral-600">
            Each curve is one expiration&apos;s implied-vol smile across moneyness. A downward-left tilt (higher put IV) is the
            equity smirk — downside insurance bid. Near expiries are brightest; the front-expiry smile is shaded.
          </p>
        </>
      )}
    </div>
  );
}
