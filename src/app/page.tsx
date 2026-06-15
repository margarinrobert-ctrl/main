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
      {config.dataSource === "fixtures" && (
        <div className="rounded border border-amber-900 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
          Running in <b>fixtures mode</b> (canned data — no API key, no quota used). Set <code>DATA_SOURCE=live</code>{" "}
          with a <code>BARCHART_API_KEY</code> to switch to live Barchart data.
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-400">Index &amp; Futures Flow</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {FOCUS.map((f) => (
            <a
              key={f.sym}
              href={withBase(`/ticker/${f.sym}`)}
              className="rounded-lg border border-neutral-800 p-3 transition hover:border-emerald-700 hover:bg-neutral-900/50"
            >
              <div className="text-lg font-semibold">{f.sym}</div>
              <div className="text-xs text-neutral-400">{f.label}</div>
              <div className="mt-2 text-[10px] text-emerald-400">flow · chart · heatmap →</div>
            </a>
          ))}
        </div>
      </section>

      <section>
        <h1 className="mb-1 text-lg font-semibold">Unusual Options Flow</h1>
        <p className="mb-4 text-sm text-neutral-400">
          Synthesized from the options screener across equities, ETFs &amp; futures. Score combines vol/OI, notional,
          volume spike, and short-dated OTM. <a className="underline" href="#how">How it works ↓</a>
        </p>
        <FlowTable />
      </section>

      <section id="how" className="max-w-2xl text-xs text-neutral-500">
        <h3 className="mb-1 font-semibold text-neutral-300">How the flow score works</h3>
        <p>
          Gates: volume ≥ 100 and open interest ≥ 50. Signals (each ramped 0–1, then weighted): vol/OI (0.4),
          volume-vs-average spike (0.2, free tier may omit), notional = vol × mid × 100 (0.3), and short-DTE + far-OTM
          (0.1). Score = weighted average × 100. All thresholds live in <code>src/lib/barchart/config.ts</code>. Click any
          ticker for its price chart, options chain, and an interactive volume/notional <b>heatmap</b>.
        </p>
      </section>
    </div>
  );
}
