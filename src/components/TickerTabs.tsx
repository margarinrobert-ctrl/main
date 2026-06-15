"use client";

import { useState } from "react";
import { GammaProfile } from "./GammaProfile";
import { KeyLevels } from "./KeyLevels";
import { OptionsChain } from "./OptionsChain";
import { OptionsHeatmap } from "./OptionsHeatmap";
import { PriceChart } from "./PriceChart";
import { QuoteCard } from "./QuoteCard";
import { SkewChart } from "./SkewChart";

const TABS = ["Overview", "Chain", "Heatmap", "Gamma", "Skew"] as const;
type Tab = (typeof TABS)[number];

export function TickerTabs({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<Tab>("Overview");
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
      {tab === "Skew" && <SkewChart symbol={symbol} />}
    </div>
  );
}
