import type { ReactNode } from "react";

/** Shimmer skeleton scaffold shown while a panel loads. */
export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="space-y-3 py-1" role="status" aria-label={label}>
      <div className="flex items-center justify-between">
        <div className="skeleton h-3.5 w-2/5" />
        <div className="skeleton h-3.5 w-16" />
      </div>
      <div className="skeleton h-28 w-full" />
      <div className="flex gap-3">
        <div className="skeleton h-14 flex-1" />
        <div className="skeleton h-14 flex-1" />
        <div className="skeleton h-14 flex-1" />
      </div>
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Structured error surface — hairline red, no alarm-panel shouting. */
export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-put/25 bg-put/[0.06] p-4" role="alert">
      <svg aria-hidden viewBox="0 0 16 16" className="mt-0.5 h-4 w-4 shrink-0 text-put">
        <path fill="currentColor" d="M8 1.5 15 14H1L8 1.5Zm-.75 5v4h1.5v-4h-1.5Zm0 5v1.5h1.5V11.5h-1.5Z" />
      </svg>
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wider text-put">Data unavailable</div>
        <div className="mt-0.5 break-words text-sm text-neutral-300">{message}</div>
      </div>
    </div>
  );
}

/** Empty surface with a crosshair motif — calm, intentional, never “default”. */
export function EmptyState({ label = "No data.", hint }: { label?: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-6 py-10 text-center">
      <svg aria-hidden viewBox="0 0 24 24" className="h-6 w-6 text-neutral-600">
        <path fill="none" stroke="currentColor" strokeWidth="1.5" d="M12 2v6m0 8v6M2 12h6m8 0h6" />
        <circle cx="12" cy="12" r="3.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <div className="text-sm text-neutral-400">{label}</div>
      {hint && <div className="max-w-xs text-[11px] leading-relaxed text-neutral-600">{hint}</div>}
    </div>
  );
}

/* ── Shared micro-primitives (adopt these instead of ad-hoc markup) ──────── */

/** Section header: micro-cap eyebrow + optional right-aligned meta. */
export function SectionHeader({ title, eyebrow, right }: { title: ReactNode; eyebrow?: string; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="lbl mb-1">{eyebrow}</div>}
        <h2 className="display text-base text-neutral-50">{title}</h2>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

/** KPI stat tile — label over value, optional delta tone. */
export function Stat({ label, value, tone, sub }: { label: string; value: ReactNode; tone?: "call" | "put" | "neutral"; sub?: ReactNode }) {
  const toneCls = tone === "call" ? "text-call" : tone === "put" ? "text-put" : "text-neutral-100";
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
      <div className="lbl">{label}</div>
      <div className={`mt-1 text-base font-semibold leading-tight ${toneCls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-neutral-500">{sub}</div>}
    </div>
  );
}

/** Inline tag chip. */
export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "call" | "put" | "accent" }) {
  const cls =
    tone === "call"
      ? "border-call/30 bg-call/10 text-call"
      : tone === "put"
        ? "border-put/30 bg-put/10 text-put"
        : tone === "accent"
          ? "border-accent/30 bg-accent/10 text-accent-bright"
          : "border-white/10 bg-white/[0.03] text-neutral-400";
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] ${cls}`}>{children}</span>;
}
