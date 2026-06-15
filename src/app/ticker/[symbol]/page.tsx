import { QuoteCard } from "@/components/QuoteCard";

export default function TickerPage({ params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  return (
    <div className="space-y-6">
      <div>
        <a href="/" className="text-xs text-neutral-400 hover:underline">
          ← back to flow
        </a>
        <h1 className="mt-1 text-lg font-semibold">{symbol}</h1>
      </div>

      <QuoteCard symbol={symbol} />

      <div className="rounded border border-neutral-800 p-4 text-sm text-neutral-500">
        Price chart (M2) and options chain + IV summary (M4) land next. Both run in fixtures mode; the live chain needs
        the PAID <code>getEquityOptions</code> endpoint.
      </div>
    </div>
  );
}
