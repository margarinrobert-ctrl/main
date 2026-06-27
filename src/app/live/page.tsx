import { LiveQuotes } from "@/components/LiveQuotes";
import { LiveStream } from "@/components/LiveStream";
import { TickerTape } from "@/components/TickerTape";
import { withBase } from "@/lib/paths";

export const metadata = { title: "Live · OptionsFlow", description: "Bloomberg-terminal-style live market news + real-time watchlist tape" };

const FKEYS = [
  { k: "EQUITY", c: "text-amber-300 border-amber-500/40 bg-amber-500/10" },
  { k: "GOVT", c: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10" },
  { k: "CMDTY", c: "text-orange-300 border-orange-500/40 bg-orange-500/10" },
  { k: "INDEX", c: "text-sky-300 border-sky-500/40 bg-sky-500/10" },
  { k: "NEWS", c: "text-red-300 border-red-500/40 bg-red-500/10" },
  { k: "HELP", c: "text-neutral-300 border-white/20 bg-white/5" },
];

export default function LivePage() {
  return (
    <div className="space-y-2 font-mono">
      {/* Bloomberg command bar */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border border-[#ffa028]/30 bg-black px-3 py-1.5 text-[11px]">
        <span className="font-bold tracking-[0.2em] text-[#ffa028]">BLOOMBERG</span>
        <span className="text-neutral-500">THE TERMINAL®</span>
        <span className="ml-auto flex flex-wrap items-center gap-1">
          {FKEYS.map((f) => (
            <span key={f.k} className={`rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold ${f.c}`}>{f.k}</span>
          ))}
        </span>
      </div>
      {/* Bloomberg amber command line */}
      <div className="flex items-center gap-2 border border-t-0 border-[#ffa028]/30 bg-black px-3 py-1 text-xs">
        <span className="text-[#ffa028]">{">"}</span>
        <span className="font-semibold tracking-wide text-[#ffa028]">LIVE</span>
        <span className="text-neutral-600">{"<GO>"}</span>
        <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-[#ffa028]" />
        <a href={withBase("/")} className="ml-auto text-[10px] uppercase tracking-[0.08em] text-neutral-500 hover:text-neutral-300">
          ← back to flow
        </a>
      </div>

      <TickerTape />

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <LiveStream />
        </div>
        <LiveQuotes />
      </div>

      <p className="text-[11px] text-neutral-600">
        Bloomberg-terminal-styled view. Live news is a third-party stream — not affiliated with Bloomberg L.P. Not financial advice.
      </p>
    </div>
  );
}
