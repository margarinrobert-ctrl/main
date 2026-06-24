export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="space-y-3 py-1" role="status" aria-label={label}>
      <div className="skeleton h-4 w-2/5" />
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

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-red-500/30 bg-red-500/[0.08] p-3.5 text-sm text-red-300">
      <span aria-hidden className="mt-px text-base leading-none">⚠</span>
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({ label = "No data." }: { label?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.02] p-6 text-center text-sm text-neutral-400">
      {label}
    </div>
  );
}
