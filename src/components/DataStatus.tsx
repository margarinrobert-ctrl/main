"use client";

import { useEffect, useState } from "react";
import { loadChain } from "@/lib/client-data";
import { assessChain, type DataStatus as Status, type IntegrityReport } from "@/lib/flow/integrity";

const tone: Record<Status, string> = {
  live: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  degraded: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  sample: "border-red-500/40 bg-red-500/10 text-red-200",
  empty: "border-white/15 bg-white/5 text-neutral-300",
};
const dot: Record<Status, string> = {
  live: "bg-emerald-400",
  degraded: "bg-amber-400",
  sample: "bg-red-400",
  empty: "bg-neutral-400",
};

export function DataStatus({ symbol }: { symbol: string }) {
  const [rep, setRep] = useState<IntegrityReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await loadChain(symbol);
        if (!cancelled) setRep(assessChain(r.chain, r.spot, r.source, r.asOf));
      } catch {
        if (!cancelled) setRep(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (!rep) return null;

  return (
    <div className={`rounded-xl border px-3 py-2 text-xs ${tone[rep.status]}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${dot[rep.status]}`} />
        <span className="font-medium">{rep.headline}</span>
        {rep.asOf && <span className="opacity-80">· CBOE as-of {rep.asOf}</span>}
        <span className="ml-auto opacity-70">{rep.contracts.toLocaleString()} contracts</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 opacity-90">
        {rep.checks.map((c) => (
          <span key={c.label} title={c.detail}>
            {c.ok ? "✓" : "⚠"} {c.label}
          </span>
        ))}
      </div>
    </div>
  );
}
