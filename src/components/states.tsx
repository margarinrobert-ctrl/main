export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="animate-pulse py-8 text-center text-sm text-neutral-400">{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-900 bg-red-950/40 p-4 text-sm text-red-400">
      {message}
    </div>
  );
}

export function EmptyState({ label = "No data." }: { label?: string }) {
  return (
    <div className="rounded border border-neutral-800 p-4 text-center text-sm text-neutral-400">{label}</div>
  );
}
