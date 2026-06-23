import { FlowTable } from "@/components/FlowTable";
import { Scanner } from "@/components/Scanner";
import { config } from "@/lib/barchart/config";
import { withBase } from "@/lib/paths";

const FOCUS = [
  { sym: "SPY", label: "S&P 500 ETF" },
  { sym: "QQQ", label: "Nasdaq-100 ETF" },
];

const CAPS = ["Signals", "Dealer GEX", "Vanna/Charm", "3D surface", "Premium Harvest", "Pine export"];

export default function Home() {
  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-2xl border border-white/10 p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-emerald-500/15 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-neutral-300">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            Options-flow &amp; dealer-gamma quant terminal
          </div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Trade the <span className="glow-text">dealer gamma</span>, harvest the <span className="glow-text">vol premium</span>.
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-neutral-400">
            Synthesized trade signals across price, volatility &amp; time — GEX positioning, vanna/charm flows, a 3D greeks
            surface, VRP premium-harvesting, a market-maker hedging algo and copy-paste TradingView levels — focused on
            <span className="text-neutral-200"> SPY &amp; QQQ</span>.
            {config.dataSource !== "live" && " Running in fixtures mode (canned data)."}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {CAPS.map((c) => (
              <span key={c} className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-neutral-300">
                {c}
              </span>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {FOCUS.map((f) => (
              <a
                key={f.sym}
                href={withBase(`/ticker/${f.sym}`)}
                className="group rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm transition hover:border-emerald-500/40 hover:bg-emerald-500/[0.06]"
              >
                <span className="font-semibold">{f.sym}</span>
                <span className="ml-2 text-xs text-neutral-500 group-hover:text-neutral-400">{f.label}</span>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section>
        <Scanner />
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
          signal board, gamma profile, greeks surface, premium-harvesting and intraday history.
        </p>
      </section>
    </div>
  );
}
