"use client";

import { useEffect, useState } from "react";
import { alertsEnabled, crossings, fireNotify } from "@/lib/alerts";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory, pullServerData } from "@/lib/client-data";
import { atmIv, callWall, gammaFlip, gexByStrike, netGex, putCallRatio, putWall } from "@/lib/flow/analytics";
import { anomalyIntel } from "@/lib/flow/anomalyPro";
import { buildSignals } from "@/lib/flow/signals";
import { mmHedge } from "@/lib/flow/mmhedge";
import { appendSample } from "@/lib/gex-history";
import { collectAndResolve } from "@/lib/intel/journal";
import { DataStatus } from "./DataStatus";
import { DexProfile } from "./DexProfile";
import { GammaProfile } from "./GammaProfile";
import { AnomalyIntel } from "./AnomalyIntel";
import { AnomalyLive } from "./AnomalyLive";
import { AnomalyScan } from "./AnomalyScan";
import { GexHistory } from "./GexHistory";
import { GexTerm } from "./GexTerm";
import { GreeksSurface } from "./GreeksSurface";
import { HarvestPanel } from "./HarvestPanel";
import { KeyLevels } from "./KeyLevels";
import { KpiRibbon } from "./KpiRibbon";
import { LevelsChart } from "./LevelsChart";
import { MMHedge } from "./MMHedge";
import { OiProfile } from "./OiProfile";
import { OptionsChain } from "./OptionsChain";
import { OptionsFlow } from "./OptionsFlow";
import { OptionsHeatmap } from "./OptionsHeatmap";
import { PineExport } from "./PineExport";
import { Playbook } from "./Playbook";
import { PriceChart } from "./PriceChart";
import { QuoteCard } from "./QuoteCard";
import { SignalBoard } from "./SignalBoard";
import { SkewChart } from "./SkewChart";
import { VannaCharmProfile } from "./VannaCharmProfile";
import { VolEdge } from "./VolEdge";
import { VolSmile } from "./VolSmile";

const TABS = [
  "Overview",
  "Signals",
  "MM Hedge",
  "Playbook",
  "Options Flow",
  "Chain",
  "Heatmap",
  "Gamma",
  "DEX",
  "Levels Chart",
  "Vanna/Charm",
  "3D",
  "Term",
  "OI",
  "Skew",
  "Smile",
  "Vol Edge",
  "Harvest",
  "Anomaly",
  "History",
  "Pine",
] as const;
type Tab = (typeof TABS)[number];

// Sidebar navigation groups (GregFlow-style section nav).
const GROUPS: { label: string; tabs: Tab[] }[] = [
  { label: "Overview", tabs: ["Overview", "Signals", "MM Hedge", "Playbook"] },
  { label: "Gamma / GEX", tabs: ["Gamma", "DEX", "Levels Chart", "OI", "Term", "3D", "Heatmap"] },
  { label: "Greeks / Vol", tabs: ["Vanna/Charm", "Skew", "Smile", "Vol Edge"] },
  { label: "Flow", tabs: ["Options Flow", "Chain", "Anomaly", "Harvest", "History", "Pine"] },
];

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

  // On open, pull anything the server collected while the site was closed and merge it locally so the
  // whole dashboard (history, anomaly, intel) reflects the full record, not just this browser session.
  useEffect(() => {
    pullServerData(symbol).catch(() => {});
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
        const exps = [...new Set(chain.map((c) => c.expiration))].sort();
        const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
        const iv = frontExp ? atmIv(chain, spot, frontExp) : null;
        const samples = appendSample(symbol, { t: Date.now(), spot, gex: netGex(chain, spot), flip, iv, pcr: putCallRatio(chain).vol });
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

        // Performance-intelligence loop: journal each engine's directional call and resolve matured
        // ones against the recorded session series. Runs while any ticker tab is open.
        if (chain.length && spot != null) {
          const { bars } = await loadHistory(symbol).catch(() => ({ bars: [] }));
          if (cancelled) return;
          const intel = anomalyIntel(symbol, chain, spot, bars, samples);
          const board = buildSignals(chain, spot, bars);
          const mm = mmHedge(chain, spot, bars);
          collectAndResolve(symbol, { chain, spot, bars, samples, intel, board, mm });
        }
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
    <div className="space-y-3">
      <DataStatus symbol={symbol} />
      <KpiRibbon symbol={symbol} />
      <div className="flex flex-col gap-4 lg:flex-row">
        {/* GregFlow-style section sidebar */}
        <aside className="lg:w-44 lg:shrink-0">
          <div className="glass p-2 lg:sticky lg:top-16">
            <label className="mb-2 block">
              <span className="lbl px-1">Expiration</span>
              <select
                value={validExp}
                onChange={(e) => setExp(e.target.value)}
                className="mt-1 w-full rounded border border-white/10 bg-neutral-900 px-2 py-1 text-xs text-neutral-100 outline-none"
              >
                {expOptions.map((o) => (
                  <option key={o.value} value={o.value} className="bg-neutral-900">
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <nav className="space-y-2">
              {GROUPS.map((g) => (
                <div key={g.label}>
                  <div className="lbl px-2 pb-1">{g.label}</div>
                  <div className="flex flex-col">
                    {g.tabs.map((t) => (
                      <button
                        key={t}
                        onClick={() => setTab(t)}
                        aria-current={tab === t ? "page" : undefined}
                        className={`rounded px-2 py-1 text-left text-xs transition ${
                          tab === t ? "border-l-2 border-l-emerald-400 bg-emerald-500/10 font-medium text-emerald-300" : "border-l-2 border-l-transparent text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </aside>

        <main className="min-w-0 flex-1 space-y-4">
          {scoped && (
            <p className="text-[11px] text-neutral-500">
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
      {tab === "MM Hedge" && <MMHedge symbol={symbol} exp={validExp} />}
      {tab === "Playbook" && <Playbook symbol={symbol} exp={validExp} />}
      {tab === "Options Flow" && <OptionsFlow symbol={symbol} exp={validExp} />}
      {tab === "Chain" && <OptionsChain symbol={symbol} exp={validExp} />}
      {tab === "Heatmap" && <OptionsHeatmap symbol={symbol} exp={validExp} />}
      {tab === "Gamma" && <GammaProfile symbol={symbol} exp={validExp} />}
      {tab === "DEX" && <DexProfile symbol={symbol} exp={validExp} />}
      {tab === "Levels Chart" && <LevelsChart symbol={symbol} />}
      {tab === "Vanna/Charm" && <VannaCharmProfile symbol={symbol} exp={validExp} />}
      {tab === "3D" && <GreeksSurface symbol={symbol} exp={validExp} />}
      {tab === "Term" && <GexTerm symbol={symbol} exp={validExp} />}
      {tab === "OI" && <OiProfile symbol={symbol} exp={validExp} />}
      {tab === "Skew" && <SkewChart symbol={symbol} exp={validExp} />}
      {tab === "Smile" && <VolSmile symbol={symbol} exp={validExp} />}
      {tab === "Vol Edge" && <VolEdge symbol={symbol} />}
      {tab === "Harvest" && <HarvestPanel symbol={symbol} exp={validExp} />}
      {tab === "Anomaly" && (
        <div className="space-y-4">
          <AnomalyIntel symbol={symbol} exp={validExp} />
          <AnomalyLive symbol={symbol} />
          <AnomalyScan symbol={symbol} />
        </div>
      )}
      {tab === "History" && <GexHistory symbol={symbol} />}
      {tab === "Pine" && <PineExport symbol={symbol} exp={validExp} />}
        </main>
      </div>
    </div>
  );
}
