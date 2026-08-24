import { DataStatus } from "@/components/DataStatus";
import { TickerTabs } from "@/components/TickerTabs";
import { withBase } from "@/lib/paths";

// Pre-rendered for the static export (GitHub Pages). On a server deploy any symbol works on demand.
export function generateStaticParams() {
  return ["SPY", "QQQ", "ES", "NQ", "AAPL", "NVDA", "TSLA", "AMD", "META"].map((symbol) => ({ symbol }));
}

export default function TickerPage({ params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[11px] text-neutral-500">
            <a href={withBase("/")} className="-mx-1 rounded px-1 py-1 uppercase tracking-wider transition hover:text-accent-bright">
              Terminal
            </a>
            <span aria-hidden>/</span>
            <span className="uppercase tracking-wider text-neutral-300">{symbol}</span>
          </nav>
          <h1 className="display mt-1 text-3xl leading-none text-neutral-50">{symbol}</h1>
          <div className="lbl mt-1.5">Options analytics · dealer positioning</div>
        </div>
      </div>
      {/* Every number below is arithmetic on this chain. If it is canned sample data because the
          live feed did not answer, that has to be said HERE, above the analytics, not buried in a
          server log. This component was written for exactly that and was imported by nothing. */}
      <DataStatus symbol={symbol} />
      <TickerTabs symbol={symbol} />
    </div>
  );
}
