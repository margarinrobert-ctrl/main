"use client";

import { useEffect, useState } from "react";
import { alertsEnabled, crossings, fireNotify } from "@/lib/alerts";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain } from "@/lib/client-data";
import { callWall, gammaFlip, gexByStrike, netGex, putWall } from "@/lib/flow/analytics";
import { appendSample } from "@/lib/gex-history";
import { DataStatus } from "./DataStatus";
import { GammaProfile } from "./GammaProfile";
import { GexHistory } from "./GexHistory";
import { GexTerm } from "./GexTerm";
import { GreeksSurface } from "./GreeksSurface";
import { HarvestPanel } from "./HarvestPanel";
import { KeyLevels } from "./KeyLevels";
import { OiProfile } from "./OiProfile";
import { OptionsChain } from "./OptionsChain";
import { OptionsHeatmap } from "./OptionsHeatmap";
import { PineExport } from "./PineExport";
import { Playbook } from "./Playbook";
import { PriceChart } from "./PriceChart";
import { QuoteCard } from "./QuoteCard";
import { SignalBoard } from "./SignalBoard";
import { SkewChart } from "./SkewChart";
import { VannaCharmProfile } from "./VannaCharmProfile";
import { VolEdge } from "./VolEdge";

const TABS = [
  "Overview",
  "Signals",
  "Playbook",
  "Chain",
  "Heatmap",
  "Gamma",
  "Vanna/Charm",
  "3D",
  "Term",
  "OI",
  "Skew",
  "Vol Edge",
  "Harvest",
  "History",
  "Pine",
] as const;
type Tab = (typeof TABS)[number];

interface ExpOption {
  value: string;
  label: string;
}

// Tabs where expiration is an axis (heatmap/term/3D) highlight the selection instead of filtering.
const AXIS_TABS = new Set<Tab>(["Heatmap", "Term", "3D"]);

function buildExpOptions(chain: OptionContract[]): ExpOption[] {
  const m = new Map<string, number | null>();
  for (const c of chain) if (!m.has(c.expiration)) m.set(c.expiration, c.dte);
  const perExp = [...m.entries()]
    .sort((a, b) => (a[1] ?? Number.MAX_SAFE_INTEGER) - (b[1] ?? Number.MAX_SAFE_INTEGER))
    .map(([e, dte]) => ({
      value: e,
      label: dte == null ? e : dte <= 0 ? `0DTE · ${e}` : `${dte}d · ${e}`,
    }));
  return [{ value: "ALL", label: "All expirations" }, ...perExp];
}

export function TickerTabs({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<Tab>("Overview");
  const [exp, setExp] = useState("ALL");
  const [expOptions, setExpOptions] = useState<ExpOption[]>([{ value: "ALL", label: "All expirations" }]);

  // Reset the expiration filter when the ticker changes.
  useEffect(() => {
    setExp("ALL");
  }, [symbol]);

  // Background sampler: records spot + net GEX + gamma flip while the ticker page is open,
  // so the History tab has an intraday series regardless of which tab is active.
  useEffect(() => {
    let cancelled = false;
    let prevSpot: number | null = null;
    const tick = async () => {
      try {
        const { chain, spot } = await loadChain(symbol);
        if (cancelled) return;
        const opts = buildExpOptions(chain);
        setExpOptions((prev) =>
          prev.length === opts.length && prev.every((o, i) => o.value === opts[i].value) ? prev : opts,
        );
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

  const validExp = expOptions.some((o) => o.value === exp) ? exp : "ALL";
  const scoped = validExp !== "ALL";

  return (
    <div className="space-y-4">
      <DataStatus symbol={symbol} />
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-1 flex-wrap gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1 backdrop-blur">
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
        <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs backdrop-blur">
          <span className="uppercase tracking-wide text-neutral-500">Expiration</span>
          <select
            value={validExp}
            onChange={(e) => setExp(e.target.value)}
            className="rounded border border-white/10 bg-neutral-900 px-2 py-1 text-neutral-100 outline-none"
          >
            {expOptions.map((o) => (
              <option key={o.value} value={o.value} className="bg-neutral-900">
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {scoped && (
        <p className="-mt-2 text-[11px] text-neutral-500">
          Scoped to <span className="text-emerald-300">{expOptions.find((o) => o.value === validExp)?.label}</span> —{" "}
          {AXIS_TABS.has(tab)
            ? "this view spans expirations, so the selection is highlighted, not filtered."
            : "levels, gamma & greeks are computed for this expiration only."}
        </p>
      )}

      {tab === "Overview" && (
        <div className="space-y-4">
          <KeyLevels symbol={symbol} exp={validExp} />
          <QuoteCard symbol={symbol} />
          <PriceChart symbol={symbol} />
        </div>
      )}
      {tab === "Signals" && <SignalBoard symbol={symbol} exp={validExp} />}
      {tab === "Playbook" && <Playbook symbol={symbol} exp={validExp} />}
      {tab === "Chain" && <OptionsChain symbol={symbol} exp={validExp} />}
      {tab === "Heatmap" && <OptionsHeatmap symbol={symbol} exp={validExp} />}
      {tab === "Gamma" && <GammaProfile symbol={symbol} exp={validExp} />}
      {tab === "Vanna/Charm" && <VannaCharmProfile symbol={symbol} exp={validExp} />}
      {tab === "3D" && <GreeksSurface symbol={symbol} exp={validExp} />}
      {tab === "Term" && <GexTerm symbol={symbol} exp={validExp} />}
      {tab === "OI" && <OiProfile symbol={symbol} exp={validExp} />}
      {tab === "Skew" && <SkewChart symbol={symbol} exp={validExp} />}
      {tab === "Vol Edge" && <VolEdge symbol={symbol} />}
      {tab === "Harvest" && <HarvestPanel symbol={symbol} exp={validExp} />}
      {tab === "History" && <GexHistory symbol={symbol} />}
      {tab === "Pine" && <PineExport symbol={symbol} exp={validExp} />}
    </div>
  );
}
