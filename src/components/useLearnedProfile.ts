"use client";

import { useEffect, useState } from "react";
import { readJournal } from "@/lib/intel/journal";
import { learnedProfile, type LearnedProfile } from "@/lib/intel/profile";

/**
 * Live view of what the Intel journal has learned, refreshed on an interval so every section stays in
 * sync as predictions resolve. SSR-safe: starts from an empty (not-ready) profile.
 */
export function useLearnedProfile(): LearnedProfile {
  const [profile, setProfile] = useState<LearnedProfile>(() => learnedProfile([]));
  useEffect(() => {
    const read = () => setProfile(learnedProfile(readJournal()));
    read();
    const ms = Math.max(15_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 30_000) || 30_000);
    const id = setInterval(read, ms);
    return () => clearInterval(id);
  }, []);
  return profile;
}
