"use client";

import type { IntelSource } from "@/lib/intel/journal";
import { calibrateConfidence, sourceStat, type LearnedProfile } from "@/lib/intel/profile";

/**
 * Compact "edge-optimized" chip shown on each directional section: how this engine has ACTUALLY
 * performed on the resolved Intel journal (realised edge + weight), and the section's stated
 * confidence recalibrated to realised hit-rates. Falls back to "learning…" until the journal matures.
 */
export function EdgeBadge({ profile, source, confidence }: { profile: LearnedProfile; source: IntelSource; confidence?: number | null }) {
  const st = sourceStat(profile, source);
  if (!profile.ready || !st || st.n < 5) {
    return (
      <span
        className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[10px] text-neutral-500"
        title="The Intel journal recalibrates this engine once enough of its calls resolve. Keep a ticker tab open (or run the 24/7 collector)."
      >
        ✦ edge: learning…
      </span>
    );
  }
  const pos = (st.edge ?? 0) >= 0;
  const cal = confidence != null ? calibrateConfidence(confidence, profile) : null;
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${pos ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-red-500/40 bg-red-500/10 text-red-300"}`}
      title={`Realised on the Intel journal: ${st.n} resolved calls · hit ${st.hitRate != null ? Math.round(st.hitRate * 100) : "—"}% · blend weight ${Math.round(st.weight * 100)}%${cal != null && confidence != null ? ` · stated ${Math.round(confidence)}% → calibrated ${cal}%` : ""}`}
    >
      ✦ edge {pos ? "+" : ""}
      {st.edge?.toFixed(2)}%/call · w{Math.round(st.weight * 100)}%
      {cal != null ? ` · cal ${cal}%` : ""}
    </span>
  );
}
