import { FuturesRR } from "@/components/FuturesRR";
import { withBase } from "@/lib/paths";

export const metadata = {
  title: "Futures R:R Quant · OptionsFlow",
  description:
    "Standalone futures risk:reward calculator with first-passage hit probabilities — the odds of tagging your take-profit before your stop, expectancy, edge and Kelly.",
};

export default function QuantPage() {
  return (
    <div className="space-y-5">
      <div>
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[11px] text-neutral-500">
          <a href={withBase("/")} className="-mx-1 rounded px-1 py-1 uppercase tracking-wider transition hover:text-accent-bright">
            Terminal
          </a>
          <span aria-hidden>/</span>
          <span className="uppercase tracking-wider text-neutral-300">Futures R:R</span>
        </nav>
        <h1 className="display mt-1 text-3xl leading-none text-neutral-50">Futures Risk : Reward</h1>
        <p className="lbl mt-1.5">Bracket-trade quant · hit probability · expectancy — no options required</p>
      </div>

      <FuturesRR />
    </div>
  );
}
