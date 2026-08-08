"use client";

import { useEffect, useState } from "react";
import { alertsEnabled, crossings, fireNotify } from "@/lib/alerts";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory, pullServerData } from "@/lib/client-data";
import { atmIv, callWall, gammaFlip, gexByStrike, netDex, netGex, putCallRatio, putWall } from "@/lib/flow/analytics";
import { anomalyIntel } from "@/lib/flow/anomalyPro";
import { buildSignals } from "@/lib/flow/signals";
import { mmHedge } from "@/lib/flow/mmhedge";
import { appendSample, readHistory } from "@/lib/gex-history";
import { collectAndResolve } from "@/lib/intel/journal";
import { groupByDay } from "@/lib/flow/historyDays";
import { loadSnapshotDays } from "@/lib/client-data";
import { DexProfile } from "./DexProfile";
import { EdgeBoard } from "./EdgeBoard";
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
import { Scenario } from "./Scenario";
import { SignalBoard } from "./SignalBoard";
import { TimeMachine } from "./TimeMachine";
import { SkewChart } from "./SkewChart";
import { VannaCharmProfile } from "./VannaCharmProfile";
import { VolEdge } from "./VolEdge";
import { VolSmile } from "./VolSmile";

const TABS = [
  "Overview",
  "Signals",
  "Edge",
  "MM Hedge",
  "Playbook",
  "Options Flow",
  "Chain",
  "Heatmap",
  "Gamma",
  "DEX",
  "Scenario",
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

// Sidebar navigation groups.
const GROUPS: { label: string; tabs: Tab[] }[] = [
  { label: "Overview", tabs: ["Overview", "Signals", "Edge", "MM Hedge", "Playbook"] },
  { label: "Gamma / GEX", tabs: ["Gamma", "DEX", "Scenario", "Levels Chart", "OI", "Term", "3D", "Heatmap"] },
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
  const [asOf, setAsOf] = useState("LIVE"); // "LIVE" or a recorded YYYY-MM-DD
  const [recordedDays, setRecordedDays] = useState<{ key: string; label: string; pts: number; snap: boolean }[]>([]);

  // Deep-link: honor ?tab= on mount (validated against the tab list).
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("tab");
    if (p && (TABS as readonly string[]).includes(p)) setTab(p as Tab);
  }, []);

  const selectTab = (t: Tab) => {
    setTab(t);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", t);
    window.history.replaceState(null, "", url.toString());
  };

  // Reset the expiration filter and any past-day selection when the ticker changes.
  useEffect(() => {
    setExp("ALL");
    setAsOf("LIVE");
  }, [symbol]);

  // Days available to browse: every day the round-the-clock collector recorded, flagged with whether a
  // per-strike snapshot exists for it. Refreshed as new samples merge in.
  useEffect(() => {
    let cancelled = false;
    const build = async () => {
      const snapDays = await loadSnapshotDays(symbol).catch(() => [] as string[]);
      if (cancelled) return;
      const snapSet = new Set(snapDays);
      const days = groupByDay(readHistory(symbol)).map((d) => ({ key: d.key, label: d.label, pts: d.samples.length, snap: snapSet.has(d.key) }));
      setRecordedDays(days);
    };
    build();
    const id = setInterval(build, 120_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol]);

  // Pull anything the 24/7 server collector recorded while the site was closed and merge it locally, so
  // the whole dashboard (history, anomaly, intel) reflects the full round-the-clock record — not just
  // this browser session. Re-pulled periodically so new server samples (collected every ~10 min by the
  // scheduled job) keep flowing in even while you sit on the History or Anomaly tab.
  useEffect(() => {
    let cancelled = false;
    const pull = () => {
      if (!cancelled) pullServerData(symbol).catch(() => {});
    };
    pull();
    const id = setInterval(pull, 120_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
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
        const samples = appendSample(symbol, { t: Date.now(), spot, gex: netGex(chain, spot), flip, iv, pcr: putCallRatio(chain).vol, dex: netDex(chain, spot) });
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

  const expSelect = (
    <div className="relative">
      <select
        value={validExp}
        onChange={(e) => setExp(e.target.value)}
        aria-label="Expiration filter"
        className="w-full appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-2 pl-3 pr-8 text-xs text-neutral-100 outline-none transition hover:border-white/20 focus:border-accent/50"
      >
        {expOptions.map((o) => (
          <option key={o.value} value={o.value} className="bg-neutral-900">
            {o.label}
          </option>
        ))}
      </select>
      <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
        <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
      </svg>
    </div>
  );

  const past = asOf !== "LIVE";
  const asOfSelect = (
    <div className="relative">
      <select
        value={asOf}
        onChange={(e) => setAsOf(e.target.value)}
        aria-label="View data as of a past day"
        className={`w-full appearance-none rounded-lg border py-2 pl-3 pr-8 text-xs outline-none transition ${
          past ? "border-amber-400/40 bg-amber-400/10 text-amber-200" : "border-white/10 bg-white/[0.03] text-neutral-100 hover:border-white/20 focus:border-accent/50"
        }`}
      >
        <option value="LIVE" className="bg-neutral-900">
          Live · now
        </option>
        {[...recordedDays].reverse().map((d) => (
          <option key={d.key} value={d.key} className="bg-neutral-900">
            {d.label}{d.snap ? " ·\u00a0strikes" : ""} · {d.pts} pts
          </option>
        ))}
        {recordedDays.length === 0 && (
          <option value="LIVE" disabled className="bg-neutral-900">
            No past days recorded yet
          </option>
        )}
      </select>
      <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
        <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
      </svg>
    </div>
  );

  const content = past ? (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.07] px-3 py-2 text-[11px] text-neutral-300">
        <span className="lbl shrink-0 text-amber-300">Past day</span>
        <span className="font-medium text-neutral-100">{recordedDays.find((d) => d.key === asOf)?.label ?? asOf}</span>
        <span className="text-neutral-400">— showing what was recorded that day. The KPI ribbon above stays live.</span>
        <button onClick={() => setAsOf("LIVE")} className="ml-auto shrink-0 rounded-md border border-white/10 px-2 py-1 font-semibold uppercase tracking-wider text-neutral-300 transition hover:border-white/25 hover:text-neutral-100">
          Back to live
        </button>
      </div>
      <TimeMachine symbol={symbol} day={asOf} onLive={() => setAsOf("LIVE")} />
    </div>
  ) : (
    <>
      {scoped && (
        <div className="flex items-center gap-2.5 rounded-lg border border-accent/25 bg-accent/[0.05] px-3 py-2 text-[11px] text-neutral-400">
          <span className="lbl shrink-0 text-accent-bright">Scope</span>
          <span className="font-medium text-neutral-200">{expOptions.find((o) => o.value === validExp)?.label}</span>
          <span className="hidden text-neutral-500 sm:inline">
            {AXIS_TABS.has(tab) ? "— this view spans expirations; the selection is highlighted, not filtered" : "— levels, gamma & greeks computed for this expiration only"}
          </span>
        </div>
      )}

      {tab === "Overview" && (
        <div className="space-y-4">
          <KeyLevels symbol={symbol} exp={validExp} />
          <QuoteCard symbol={symbol} />
          <PriceChart symbol={symbol} />
        </div>
      )}
      {tab === "Signals" && <SignalBoard symbol={symbol} exp={validExp} />}
      {tab === "Edge" && <EdgeBoard symbol={symbol} exp={validExp} />}
      {tab === "MM Hedge" && <MMHedge symbol={symbol} exp={validExp} />}
      {tab === "Playbook" && <Playbook symbol={symbol} exp={validExp} />}
      {tab === "Options Flow" && <OptionsFlow symbol={symbol} exp={validExp} />}
      {tab === "Chain" && <OptionsChain symbol={symbol} exp={validExp} />}
      {tab === "Heatmap" && <OptionsHeatmap symbol={symbol} exp={validExp} />}
      {tab === "Gamma" && <GammaProfile symbol={symbol} exp={validExp} />}
      {tab === "DEX" && <DexProfile symbol={symbol} exp={validExp} />}
      {tab === "Scenario" && <Scenario symbol={symbol} exp={validExp} />}
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
    </>
  );

  return (
    <div className="space-y-3">
      <KpiRibbon symbol={symbol} />

      {/* Mobile: expiration + horizontal module scroller (sticky under the header). */}
      <div className="sticky top-[53px] z-10 -mx-4 space-y-2 border-b border-white/[0.06] bg-[#05060a]/85 px-4 py-2 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:hidden">
        <div className="grid grid-cols-2 gap-2">
          {asOfSelect}
          {expSelect}
        </div>
        <div className="tabs-scroll -mx-1 px-1 pb-0.5">
          {GROUPS.map((g, gi) => (
            <div key={g.label} className="flex items-center gap-1">
              {gi > 0 && <span aria-hidden className="mx-1.5 h-4 w-px shrink-0 bg-white/10" />}
              {g.tabs.map((t) => (
                <button
                  key={t}
                  onClick={() => selectTab(t)}
                  aria-current={tab === t ? "page" : undefined}
                  className={`tab-pill rounded-lg px-3 py-2 text-xs font-medium transition ${
                    tab === t ? "bg-accent/15 text-accent-bright shadow-glow-accent" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row">
        {/* Desktop: section rail */}
        <aside className="hidden lg:block lg:w-48 lg:shrink-0">
          <div className="glass p-2.5 lg:sticky lg:top-16">
            <label className="mb-2.5 block">
              <span className="lbl px-1">Date</span>
              <div className="mt-1.5">{asOfSelect}</div>
            </label>
            <label className="mb-3 block">
              <span className="lbl px-1">Expiration</span>
              <div className="mt-1.5">{expSelect}</div>
            </label>
            <nav className="space-y-3" aria-label="Analytics modules">
              {GROUPS.map((g) => (
                <div key={g.label}>
                  <div className="lbl px-2 pb-1.5">{g.label}</div>
                  <div className="flex flex-col gap-px">
                    {g.tabs.map((t) => (
                      <button
                        key={t}
                        onClick={() => selectTab(t)}
                        aria-current={tab === t ? "page" : undefined}
                        className={`rounded-md border-l-2 px-2.5 py-1.5 text-left text-xs transition ${
                          tab === t
                            ? "border-l-accent-bright bg-accent/[0.08] font-medium text-accent-bright"
                            : "border-l-transparent text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"
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

        <main className="min-w-0 flex-1">
          <div key={tab} className="fade-up space-y-4">
            {content}
          </div>
        </main>
      </div>
    </div>
  );
}
