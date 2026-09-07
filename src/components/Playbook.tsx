"use client";

import { useEffect, useMemo, useState } from "react";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { filterByExpiration } from "@/lib/flow/analytics";
import { buildPlaybook, type Side } from "@/lib/flow/playbook";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sideStyles: Record<Side, { chip: string; border: string; label: string }> = {
  bullish: { chip: "border-call/30 bg-call/10 text-call", border: "border-l-call/80", label: "Bullish" },
  bearish: { chip: "border-put/30 bg-put/10 text-put", border: "border-l-put/80", label: "Bearish" },
  neutral: { chip: "border-white/10 bg-white/[0.03] text-neutral-300", border: "border-l-accent-cyan/60", label: "Neutral" },
};

export function Playbook({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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

  const pb = useMemo(() => buildPlaybook(filterByExpiration(chain, exp), spot), [chain, spot, exp]);

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Intraday playbook" title={symbol} right={<span className="lbl">Bias from dealer gamma positioning</span>} />

      {state === "loading" && <Loading label="Loading gamma profile…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for a playbook." hint="The playbook builds from the option chain's dealer-gamma profile." />}
      {state === "ok" && (
        <>
          <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
                  pb.regime === "long"
                    ? "border-call/30 bg-call/10 text-call"
                    : pb.regime === "short"
                      ? "border-put/30 bg-put/10 text-put"
                      : "border-white/10 bg-white/[0.03] text-neutral-300"
                }`}
              >
                {pb.regime === "long" ? "Long γ · mean-revert" : pb.regime === "short" ? "Short γ · momentum" : "γ n/a"}
              </span>
              <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${sideStyles[pb.bias].chip}`}>
                Bias · {sideStyles[pb.bias].label}
              </span>
            </div>
            <div className="lbl mt-3">Regime read</div>
            <p className="mt-1 text-sm leading-relaxed text-neutral-300">{pb.regimeText}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-neutral-400">{pb.biasText}</p>
          </div>

          <div className="stagger space-y-2">
            {pb.plays.map((p) => (
              <div
                key={p.title}
                className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3.5 transition-colors hover:border-white/[0.14] hover:bg-white/[0.035] ${sideStyles[p.side].border}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-neutral-100">{p.title}</span>
                  <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] ${sideStyles[p.side].chip}`}>
                    {sideStyles[p.side].label} · {p.bias}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-neutral-400">{p.detail}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 border-t border-white/[0.05] pt-3">
            <div className="lbl mb-1.5">Model notes</div>
            <div className="space-y-1">
              {pb.notes.map((n) => (
                <p key={n} className="text-[11px] leading-relaxed text-neutral-500">
                  {n}
                </p>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
