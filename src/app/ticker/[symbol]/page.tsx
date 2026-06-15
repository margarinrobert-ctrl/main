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
      <div>
        <a href={withBase("/")} className="text-xs text-neutral-400 hover:underline">
          ← back to flow
        </a>
        <h1 className="mt-1 text-lg font-semibold">{symbol}</h1>
      </div>
      <TickerTabs symbol={symbol} />
    </div>
  );
}
