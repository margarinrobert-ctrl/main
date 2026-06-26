"use client";

import { useState } from "react";

// Public 24/7 finance live streams (YouTube channel live-embed). Bloomberg's own player isn't
// embeddable, so we default to its YouTube channel live and link out to bloomberg.com/live/us.
const SOURCES = [
  { id: "bloomberg", label: "Bloomberg TV", channel: "UCIALMKvObZNtJ6AmdCLP7Lg" },
  { id: "yahoo", label: "Yahoo Finance", channel: "UCEAZeUIeJs0IjQiqTCdVSIg" },
  { id: "cnbc", label: "CNBC", channel: "UCvJJ_dzjViJCoLf5uKUTwoA" },
] as const;

function parseYouTube(s: string): string | null {
  const t = s.trim();
  if (!t) return null;
  const m = t.match(/(?:v=|youtu\.be\/|\/embed\/|\/live\/|\/shorts\/)([\w-]{6,})/);
  if (m) return m[1];
  if (/^[\w-]{8,}$/.test(t)) return t; // looks like a raw video id
  return null;
}

const chip = (active: boolean) =>
  `rounded px-2 py-1 text-xs transition ${active ? "bg-emerald-500/15 text-emerald-300" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`;

export function LiveStream() {
  const [src, setSrc] = useState<(typeof SOURCES)[number]>(SOURCES[0]);
  const [custom, setCustom] = useState("");
  const customId = parseYouTube(custom);
  const embed = customId
    ? `https://www.youtube.com/embed/${customId}?autoplay=1&mute=1`
    : `https://www.youtube.com/embed/live_stream?channel=${src.channel}&autoplay=1&mute=1`;

  return (
    <div className="glass p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="lbl">Live stream</span>
        {SOURCES.map((s) => (
          <button key={s.id} onClick={() => { setSrc(s); setCustom(""); }} className={chip(src.id === s.id && !customId)}>
            {s.label}
          </button>
        ))}
        <input
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          placeholder="paste YouTube URL / ID…"
          className="min-w-[160px] flex-1 rounded border border-white/10 bg-neutral-900 px-2 py-1 text-xs text-neutral-100 outline-none placeholder:text-neutral-600"
        />
        <a
          href="https://www.bloomberg.com/live/us"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded border border-white/10 px-2 py-1 text-xs text-neutral-300 hover:bg-white/5"
        >
          Bloomberg Live ↗
        </a>
      </div>
      <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-white/10 bg-black">
        <iframe
          key={embed}
          src={embed}
          title="Live market news"
          className="absolute inset-0 h-full w-full"
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
          allowFullScreen
        />
      </div>
      <p className="mt-2 text-[11px] text-neutral-500">
        Third-party YouTube live — availability depends on the broadcaster being on air. Paste any YouTube URL/ID to
        override, or open the native <span className="text-neutral-300">Bloomberg Live ↗</span> feed.
      </p>
    </div>
  );
}
