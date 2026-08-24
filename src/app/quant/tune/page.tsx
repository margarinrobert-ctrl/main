import { TunerConsole } from "@/components/TunerConsole";
import { withBase } from "@/lib/paths";

export const metadata = {
  title: "Tuner",
  description: "Tune indicator periods, session window, entry and exit geometry against a research/locked split, in the browser.",
};

export default function TunePage() {
  return (
    <div className="space-y-3">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 font-mono text-[11px] text-neutral-500">
        <a href={withBase("/")} className="-mx-1 inline-flex min-h-9 items-center rounded px-1 uppercase tracking-wider transition hover:text-accent-bright">
          Terminal
        </a>
        <span aria-hidden>/</span>
        <span className="uppercase tracking-wider text-neutral-300">Tuner</span>
      </nav>

      <header className="rounded-panel border border-white/[0.06] bg-white/[0.015] p-4 shadow-panel">
        <h1 className="text-lg font-semibold tracking-tightest text-neutral-100">Strategy tuner</h1>
        <p className="mt-1.5 max-w-3xl text-[12px] leading-relaxed text-neutral-400">
          Indicator periods, trading window, entry side and the two exits — stop and target — turned as knobs rather than edited as code. A trade&apos;s outcome
          depends only on the bar it was signalled from and the geometry, so the price walk is cached once per geometry across every bar; after that a rule is a
          mask and each configuration is a few microseconds.
        </p>
        <p className="mt-2 max-w-3xl text-[12px] leading-relaxed text-neutral-500">
          The engine is asserted against <code className="text-neutral-400">runBacktest</code> trade for trade — same count, same entry bar, same exit bar, same
          P&amp;L — so a number here is the same number the study scripts produce, only faster to get.
        </p>
      </header>

      <TunerConsole />

      <p className="px-1 font-mono text-[11px] leading-relaxed text-neutral-600">
        Research tooling for education and analysis. Not financial advice, and nothing here justifies risk capital.
      </p>
    </div>
  );
}
