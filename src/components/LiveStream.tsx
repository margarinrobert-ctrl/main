"use client";

// Bloomberg Television live on YouTube. Channel-live embeds are unreliable ("video unavailable"),
// so we pin the live video id (override via NEXT_PUBLIC_LIVE_VIDEO_ID if the stream rotates).
// youtube-nocookie + modestbranding + a top mask keep the YouTube chrome out of sight.
const VIDEO_ID = process.env.NEXT_PUBLIC_LIVE_VIDEO_ID || "QB5BNdBFujE";
const EMBED = `https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1&mute=1&playsinline=1&modestbranding=1&rel=0&iv_load_policy=3&color=white`;

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
        {/* mask the YouTube title/avatar strip so it reads as a native Bloomberg feed */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-12 bg-gradient-to-b from-black via-black/70 to-transparent" />
      </div>
      <p className="mt-2 font-mono text-[11px] text-neutral-600">Bloomberg TV live · hover for sound &amp; fullscreen.</p>
    </div>
  );
}
