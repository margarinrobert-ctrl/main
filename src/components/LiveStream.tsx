"use client";

// Bloomberg Television 24/7 live (YouTube channel live-embed). Bloomberg's own player isn't
// embeddable, so this uses its public YouTube channel feed.
const BLOOMBERG_CHANNEL = "UCIALMKvObZNtJ6AmdCLP7Lg";
const EMBED = `https://www.youtube.com/embed/live_stream?channel=${BLOOMBERG_CHANNEL}&autoplay=1&mute=1`;

export function LiveStream() {
  return (
    <div className="border border-[#ffa028]/30 bg-black p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="relative inline-flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/70" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
        </span>
        <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#ffa028]">Bloomberg Television · Live</span>
      </div>
      <div className="relative aspect-video w-full overflow-hidden border border-[#ffa028]/20 bg-black">
        <iframe
          src={EMBED}
          title="Bloomberg Television Live"
          className="absolute inset-0 h-full w-full"
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
          allowFullScreen
        />
      </div>
      <p className="mt-2 font-mono text-[11px] text-neutral-600">Bloomberg TV live — if the screen is dark the channel is briefly off-air between live segments.</p>
    </div>
  );
}
