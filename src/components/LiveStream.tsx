"use client";

import { useRef, useState } from "react";

// Live market television embed. We hide all player chrome (controls=0) and put a transparent
// click-blocker over the player so nothing — logo, title, outbound link — can open an external
// page. Sound is driven by our own button via the iframe API (postMessage), so the user never
// touches a player control. Pin the live id (override with NEXT_PUBLIC_LIVE_VIDEO_ID if it rotates).
const VIDEO_ID = process.env.NEXT_PUBLIC_LIVE_VIDEO_ID || "QB5BNdBFujE";
const EMBED = `https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1&mute=1&playsinline=1&controls=0&disablekb=1&fs=0&modestbranding=1&rel=0&iv_load_policy=3&enablejsapi=1`;

export function LiveStream() {
  const ref = useRef<HTMLIFrameElement>(null);
  const [muted, setMuted] = useState(true);
  const [loaded, setLoaded] = useState(false);

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
    <div className="rounded-xl border border-amber-400/20 bg-base p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="live-dot" />
        <span className="lbl text-amber-400">Market Television · Live</span>
        <button
          onClick={toggleSound}
          aria-pressed={!muted}
          className="ml-auto inline-flex min-h-9 items-center rounded-lg border border-amber-400/30 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-amber-400 transition hover:bg-amber-400/10"
        >
          {muted ? "Unmute" : "Mute"}
        </button>
      </div>
      <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-white/10 bg-base">
        {!loaded && <div className="skeleton absolute inset-0 rounded-lg" />}
        <iframe
          ref={ref}
          src={EMBED}
          title="Market television live stream"
          className="absolute inset-0 h-full w-full"
          allow="autoplay; encrypted-media"
          onLoad={() => setLoaded(true)}
        />
        {/* visual mask over the player title strip */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-12 bg-gradient-to-b from-black via-black/70 to-transparent" />
        {/* full transparent click-blocker → no player logo/icon/link can open an external page */}
        <div className="absolute inset-0 z-20 cursor-default" aria-hidden />
      </div>
      <p className="mt-2 font-mono text-[11px] text-neutral-500">Continuous market coverage · audio muted by default.</p>
    </div>
  );
}
