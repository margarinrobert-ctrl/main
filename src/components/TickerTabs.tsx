"use client";

import { useEffect, useState } from "react";
import { loadChain } from "@/lib/client-data";
import { gammaFlip, gexByStrike, netGex } from "@/lib/flow/analytics";
import { appendSample } from "@/lib/gex-history";
import { GammaProfile } from "./GammaProfile";
import { GexHistory } from "./GexHistory";
import { KeyLevels } from "./KeyLevels";
import { OiProfile } from "./OiProfile";
import { OptionsChain } from "./OptionsChain";
import { OptionsHeatmap } from "./OptionsHeatmap";
import { PriceChart } from "./PriceChart";
import { QuoteCard } from "./QuoteCard";
import { SkewChart } from "./SkewChart";

const TABS = ["Overview", "Chain", "Heatmap", "Gamma", "OI", "Skew", "History"] as const;
type Tab = (typeof TABS)[number];

export function TickerTabs({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<Tab>("Overview");

  // Background sampler: records spot + net GEX + gamma flip while the ticker page is open,
  // so the History tab has an intraday series regardless of which tab is active.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const { chain, spot } = await loadChain(symbol);
        if (cancelled) return;
        const by = gexByStrike(chain, spot);
        appendSample(symbol, { t: Date.now(), spot, gex: netGex(chain, spot), flip: gammaFlip(by) });
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
      <div className="flex flex-wrap gap-1 border-b border-neutral-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm transition ${
              tab === t ? "border-b-2 border-emerald-400 font-medium text-emerald-400" : "text-neutral-400 hover:text-neutral-200"
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
      {tab === "OI" && <OiProfile symbol={symbol} />}
      {tab === "Skew" && <SkewChart symbol={symbol} />}
      {tab === "History" && <GexHistory symbol={symbol} />}
    </div>
  );
}
