import { FlowTable } from "@/components/FlowTable";
import { QuoteCard } from "@/components/QuoteCard";
import { config } from "@/lib/barchart/config";

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
        <h1 className="mb-1 text-lg font-semibold">Unusual Options Flow</h1>
        <p className="mb-4 text-sm text-neutral-400">
          Synthesized from the options screener. Score combines vol/OI, notional, volume spike, and short-dated OTM.{" "}
          <a className="underline" href="#how">
            How it works ↓
          </a>
        </p>
        <FlowTable />
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold">Quote (vertical-slice demo)</h2>
        <QuoteCard symbol="AAPL" />
      </section>

      <section id="how" className="max-w-2xl text-xs text-neutral-500">
        <h3 className="mb-1 font-semibold text-neutral-300">How the flow score works</h3>
        <p>
          Gates: volume ≥ 100 and open interest ≥ 50. Signals (each ramped 0–1, then weighted): vol/OI (0.4),
          volume-vs-average spike (0.2, free tier may omit), notional = vol × mid × 100 (0.3), and short-DTE + far-OTM
          (0.1). Score = weighted average × 100. All thresholds live in{" "}
          <code>src/lib/barchart/config.ts</code>.
        </p>
      </section>
    </div>
  );
}
