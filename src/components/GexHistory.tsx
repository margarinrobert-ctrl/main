"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtUsd } from "@/lib/flow/analytics";
import { type GexSample, readHistory } from "@/lib/gex-history";
import { EmptyState } from "./states";

export function GexHistory({ symbol }: { symbol: string }) {
  const [series, setSeries] = useState<GexSample[]>([]);

  useEffect(() => {
    setSeries(readHistory(symbol));
    const id = setInterval(() => setSeries(readHistory(symbol)), 5000);
    return () => clearInterval(id);
  }, [symbol]);

  const data = useMemo(
    () =>
      series.map((s) => ({
        time: new Date(s.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        spot: s.spot,
        gex: s.gex,
      })),
    [series],
  );

  return (
    <div className="glass p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">History · {symbol}</h2>
        <span className="text-xs text-neutral-500">spot &amp; net GEX over the session</span>
      </div>

      {data.length < 2 ? (
        <EmptyState label="Collecting… intraday history builds while the ticker is open (a point every ~minute) and persists in your browser." />
      ) : (
        <>
          <div className="h-[340px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="#262626" />
                <XAxis dataKey="time" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" minTickGap={40} />
                <YAxis
                  yAxisId="spot"
                  tick={{ fill: "#a3a3a3", fontSize: 11 }}
                  stroke="#404040"
                  width={64}
                  domain={["auto", "auto"]}
                />
                <YAxis
                  yAxisId="gex"
                  orientation="right"
                  tickFormatter={(v) => fmtUsd(Number(v))}
                  tick={{ fill: "#a3a3a3", fontSize: 11 }}
                  stroke="#404040"
                  width={64}
                  domain={["auto", "auto"]}
                />
                <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }} />
                <ReferenceLine yAxisId="gex" y={0} stroke="#525252" />
                <Line yAxisId="spot" type="monotone" dataKey="spot" name="Spot" stroke="#e5e5e5" dot={false} strokeWidth={2} connectNulls />
                <Line yAxisId="gex" type="monotone" dataKey="gex" name="Net GEX" stroke="#34d399" dot={false} strokeWidth={2} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-neutral-500">
            Recorded locally as you watch ({data.length} points). For server-side multi-day history, the Postgres + cron
            layer is the upgrade.
          </p>
        </>
      )}
    </div>
  );
}
