import { FlowTable } from "@/components/FlowTable";
import { config } from "@/lib/barchart/config";
import { withBase } from "@/lib/paths";

const FOCUS = [
  { sym: "SPY", label: "S&P 500 ETF" },
  { sym: "QQQ", label: "Nasdaq-100 ETF" },
  { sym: "ES", label: "S&P E-mini Future" },
  { sym: "NQ", label: "Nasdaq E-mini Future" },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-emerald-500/10 via-transparent to-cyan-500/10 p-6">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          Unusual Options <span className="glow-text">Flow</span> &amp; Dealer Gamma
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-neutral-400">
          Live options flow, GEX positioning, heatmaps and skew across equities, ETFs &amp; index futures.
          {config.dataSource !== "live" && " Running in fixtures mode (canned data)."}
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-widest text-neutral-500">Index &amp; Futures</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {FOCUS.map((f) => (
            <a key={f.sym} href={withBase(`/ticker/${f.sym}`)} className="glass glass-hover p-4">
              <div className="text-lg font-semibold">{f.sym}</div>
              <div className="text-xs text-neutral-400">{f.label}</div>
              <div className="mt-2 text-[10px] font-medium text-emerald-400">flow · gamma · heatmap →</div>
            </a>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-lg font-semibold">Unusual Options Flow</h2>
          <a className="text-xs text-neutral-400 underline-offset-2 hover:underline" href="#how">
            how scoring works ↓
          </a>
        </div>
        <div className="glass p-4">
          <FlowTable />
        </div>
      </section>

      <section id="how" className="max-w-2xl text-xs text-neutral-500">
        <h3 className="mb-1 font-semibold text-neutral-300">How the flow score works</h3>
        <p>
          Gates: volume ≥ 100 and open interest ≥ 50. Signals (each ramped 0–1, then weighted): vol/OI (0.4),
          volume-vs-average spike (0.2), notional = vol × mid × multiplier (0.3), short-DTE + far-OTM (0.1). Score =
          weighted average × 100. Thresholds live in <code>src/lib/barchart/config.ts</code>. Click any ticker for its
          chain, gamma profile, OI, skew, and intraday history.
        </p>
      </section>
    </div>
  );
}
