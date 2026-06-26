import { LiveQuotes } from "@/components/LiveQuotes";
import { LiveStream } from "@/components/LiveStream";
import { TickerTape } from "@/components/TickerTape";
import { withBase } from "@/lib/paths";

export const metadata = { title: "Live · OptionsFlow", description: "Live market news stream + a real-time watchlist tape" };

export default function LivePage() {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="brand flex items-center gap-2.5 text-xl text-neutral-50">
          LIVE
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-red-300">
            <span className="relative inline-flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/70" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
            </span>
            US Markets
          </span>
        </h1>
        <a href={withBase("/")} className="lbl hover:text-neutral-300">← back to flow</a>
      </div>

      <TickerTape />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <LiveStream />
        </div>
        <LiveQuotes />
      </div>

      <p className="text-[11px] text-neutral-600">
        Live news is a third-party stream; quotes are delayed (free feed) and for research only. Not financial advice.
      </p>
    </div>
  );
}
