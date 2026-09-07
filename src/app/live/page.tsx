import { LiveQuotes } from "@/components/LiveQuotes";
import { LiveStream } from "@/components/LiveStream";
import { TickerTape } from "@/components/TickerTape";
import { withBase } from "@/lib/paths";

export const metadata = { title: "Live · OptionsFlow", description: "Live market television and a real-time watchlist tape" };

const FKEYS = [
  { k: "EQUITY", accent: true },
  { k: "GOVT", accent: true },
  { k: "CMDTY", accent: true },
  { k: "INDEX", accent: true },
  { k: "NEWS", accent: true },
  { k: "HELP", accent: false },
];

export default function LivePage() {
  return (
    <div className="space-y-3 font-mono">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[11px] text-neutral-500">
        <a
          href={withBase("/")}
          className="-mx-1 inline-flex min-h-9 items-center rounded px-1 uppercase tracking-wider transition hover:text-accent-bright"
        >
          Terminal
        </a>
        <span aria-hidden>/</span>
        <span className="uppercase tracking-wider text-neutral-300">Live</span>
      </nav>

      {/* Command bar + command line */}
      <div className="fade-up divide-y divide-white/5 overflow-hidden rounded-xl border border-amber-400/20 bg-base">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2 text-[11px]">
          <span className="font-bold tracking-[0.2em] text-amber-400">OPTIONSFLOW LIVE</span>
          <span className="text-neutral-500">MARKET TELEVISION</span>
          <span className="ml-auto flex flex-wrap items-center gap-1">
            {FKEYS.map((f) => (
              <span
                key={f.k}
                className={`lbl rounded border px-1.5 py-1 ${
                  f.accent ? "border-amber-400/30 bg-amber-400/10 text-amber-300" : "border-white/10 bg-white/5 text-neutral-400"
                }`}
              >
                {f.k}
              </span>
            ))}
          </span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 text-xs">
          <span className="text-amber-400">{">"}</span>
          <span className="font-semibold tracking-wide text-amber-400">LIVE</span>
          <span className="text-neutral-600">{"<GO>"}</span>
          <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-amber-400" />
          <span className="ml-auto inline-flex items-center gap-1.5">
            <span className="live-dot" />
            <span className="lbl">Streaming</span>
          </span>
        </div>
      </div>

      <TickerTape />

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <LiveStream />
        </div>
        <LiveQuotes />
      </div>

      <p className="text-[11px] text-neutral-600">Not financial advice.</p>
    </div>
  );
}
