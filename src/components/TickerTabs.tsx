"use client";

import { useEffect, useState } from "react";
import { alertsEnabled, crossings, fireNotify } from "@/lib/alerts";
import { loadChain } from "@/lib/client-data";
import { callWall, gammaFlip, gexByStrike, netGex, putWall } from "@/lib/flow/analytics";
import { appendSample } from "@/lib/gex-history";
import { GammaProfile } from "./GammaProfile";
import { GexHistory } from "./GexHistory";
import { GexTerm } from "./GexTerm";
import { KeyLevels } from "./KeyLevels";
import { OiProfile } from "./OiProfile";
import { OptionsChain } from "./OptionsChain";
import { OptionsHeatmap } from "./OptionsHeatmap";
import { PineExport } from "./PineExport";
import { PriceChart } from "./PriceChart";
import { QuoteCard } from "./QuoteCard";
import { SkewChart } from "./SkewChart";

const TABS = ["Overview", "Chain", "Heatmap", "Gamma", "Term", "OI", "Skew", "History", "Pine"] as const;
type Tab = (typeof TABS)[number];

export function TickerTabs({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<Tab>("Overview");

  // Background sampler: records spot + net GEX + gamma flip while the ticker page is open,
  // so the History tab has an intraday series regardless of which tab is active.
  useEffect(() => {
    let cancelled = false;
    let prevSpot: number | null = null;
    const tick = async () => {
      try {
        const { chain, spot } = await loadChain(symbol);
        if (cancelled) return;
        const by = gexByStrike(chain, spot);
        const flip = gammaFlip(by);
        appendSample(symbol, { t: Date.now(), spot, gex: netGex(chain, spot), flip });
        if (alertsEnabled(symbol) && prevSpot != null && spot != null) {
          const crossed = crossings(prevSpot, spot, [
            { name: "γ-flip", value: flip },
            { name: "Call wall", value: callWall(by) },
            { name: "Put wall", value: putWall(by) },
          ]);
          for (const lvl of crossed) {
            fireNotify(`${symbol} crossed ${lvl.name}`, `Spot ${spot} crossed ${lvl.name} ${lvl.value}`);
          }
        }
        prevSpot = spot;
      } catch {
        /* ignore — history just won't gain a point this cycle */
      }
    };
    tick();
    const ms = Math.max(30_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60_000) || 60_000);
    const id = setInterval(tick, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1 backdrop-blur">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm transition ${
              tab === t
                ? "bg-emerald-500/15 font-medium text-emerald-300 shadow-[0_0_14px_-3px_rgba(16,185,129,0.6)]"
                : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-4">
          <KeyLevels symbol={symbol} />
          <QuoteCard symbol={symbol} />
          <PriceChart symbol={symbol} />
        </div>
      )}
      {tab === "Chain" && <OptionsChain symbol={symbol} />}
      {tab === "Heatmap" && <OptionsHeatmap symbol={symbol} />}
      {tab === "Gamma" && <GammaProfile symbol={symbol} />}
      {tab === "Term" && <GexTerm symbol={symbol} />}
      {tab === "OI" && <OiProfile symbol={symbol} />}
      {tab === "Skew" && <SkewChart symbol={symbol} />}
      {tab === "History" && <GexHistory symbol={symbol} />}
      {tab === "Pine" && <PineExport symbol={symbol} />}
    </div>
  );
}
