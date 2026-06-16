"use client";

import { useEffect, useMemo, useState } from "react";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { buildPlaybook, type Side } from "@/lib/flow/playbook";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sideStyles: Record<Side, { chip: string; border: string; label: string }> = {
  bullish: { chip: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40", border: "border-l-emerald-500", label: "Bullish" },
  bearish: { chip: "bg-red-500/15 text-red-300 border-red-500/40", border: "border-l-red-500", label: "Bearish" },
  neutral: { chip: "bg-neutral-500/15 text-neutral-300 border-neutral-500/40", border: "border-l-neutral-500", label: "Neutral" },
};

export function Playbook({ symbol }: { symbol: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [source, setSource] = useState("");
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
        setSource(res.source);
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

  const pb = useMemo(() => buildPlaybook(chain, spot), [chain, spot]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Intraday Playbook · {symbol}</h2>
        <span className="text-xs text-neutral-500">scalping bias from dealer gamma · src: {source}</span>
      </div>

      {state === "loading" && <Loading label="Reading the tape…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data to build a playbook." />}
      {state === "ok" && (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-sm font-medium ${
                pb.regime === "long"
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                  : pb.regime === "short"
                    ? "border-red-500/40 bg-red-500/10 text-red-300"
                    : "border-white/15 text-neutral-300"
              }`}
            >
              {pb.regime === "long" ? "Long γ · mean-revert" : pb.regime === "short" ? "Short γ · momentum" : "γ n/a"}
            </span>
            <span className={`rounded-full border px-3 py-1 text-sm font-medium ${sideStyles[pb.bias].chip}`}>
              Bias: {sideStyles[pb.bias].label}
            </span>
          </div>

          <p className="mb-1 text-sm text-neutral-300">{pb.regimeText}</p>
          <p className="mb-4 text-sm text-neutral-400">{pb.biasText}</p>

          <div className="space-y-2">
            {pb.plays.map((p) => (
              <div key={p.title} className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-3 ${sideStyles[p.side].border}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-neutral-100">{p.title}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] ${sideStyles[p.side].chip}`}>
                    {sideStyles[p.side].label} · {p.bias}
                  </span>
                </div>
                <p className="mt-1 text-xs text-neutral-400">{p.detail}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 space-y-1">
            {pb.notes.map((n) => (
              <p key={n} className="text-[11px] text-neutral-500">
                {n}
              </p>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
