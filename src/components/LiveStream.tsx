"use client";

import { useRef, useState } from "react";

// Bloomberg Television live on YouTube. We hide all YouTube chrome (controls=0) and put a transparent
// click-blocker over the player so nothing — logo, title, "watch on YouTube" — can open an external
// page. Sound is driven by our own button via the YouTube iframe API (postMessage), so the user never
// touches a YouTube control. Pin the live id (override with NEXT_PUBLIC_LIVE_VIDEO_ID if it rotates).
const VIDEO_ID = process.env.NEXT_PUBLIC_LIVE_VIDEO_ID || "QB5BNdBFujE";
const EMBED = `https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1&mute=1&playsinline=1&controls=0&disablekb=1&fs=0&modestbranding=1&rel=0&iv_load_policy=3&enablejsapi=1`;

export function LiveStream() {
  const ref = useRef<HTMLIFrameElement>(null);
  const [muted, setMuted] = useState(true);

  const cmd = (func: string) =>
    ref.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args: [] }), "*");

  const toggleSound = () => {
    if (muted) {
      cmd("unMute");
      cmd("playVideo");
      setMuted(false);
    } else {
      cmd("mute");
      setMuted(true);
    }
  };

  return (
    <div className="border border-[#ffa028]/30 bg-black p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="relative inline-flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/70" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
        </span>
        <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#ffa028]">Bloomberg Television · Live</span>
        <button
          onClick={toggleSound}
          className="ml-auto rounded border border-[#ffa028]/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#ffa028] transition hover:bg-[#ffa028]/10"
        >
          {muted ? "🔇 Muted" : "🔊 Sound"}
        </button>
      </div>
      <div className="relative aspect-video w-full overflow-hidden border border-[#ffa028]/20 bg-black">
        <iframe
          ref={ref}
          src={EMBED}
          title="Bloomberg Television Live"
          className="absolute inset-0 h-full w-full"
          allow="autoplay; encrypted-media"
        />
        {/* visual mask over the YouTube title/avatar strip */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-12 bg-gradient-to-b from-black via-black/70 to-transparent" />
        {/* full transparent click-blocker → no YouTube logo/icon/link can open an external page */}
        <div className="absolute inset-0 z-20 cursor-default" aria-hidden />
      </div>
      <p className="mt-2 font-mono text-[11px] text-neutral-600">Bloomberg TV live · use the Sound toggle — no external links open.</p>
    </div>
  );
}
