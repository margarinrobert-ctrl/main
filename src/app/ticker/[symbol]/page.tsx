import { OptionsChain } from "@/components/OptionsChain";
import { PriceChart } from "@/components/PriceChart";
import { QuoteCard } from "@/components/QuoteCard";
import { withBase } from "@/lib/paths";

// Pre-rendered for the static export (GitHub Pages). On a server deploy any symbol works on demand.
export function generateStaticParams() {
  return ["AAPL", "NVDA", "TSLA", "SPY", "AMD", "META", "GOOGL", "MSFT", "F", "PLTR"].map((symbol) => ({ symbol }));
}

export default function TickerPage({ params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  return (
    <div className="space-y-6">
      <div>
        <a href={withBase("/")} className="text-xs text-neutral-400 hover:underline">
          ← back to flow
        </a>
        <h1 className="mt-1 text-lg font-semibold">{symbol}</h1>
      </div>

      <QuoteCard symbol={symbol} />
      <PriceChart symbol={symbol} />
      <OptionsChain symbol={symbol} />
    </div>
  );
}
