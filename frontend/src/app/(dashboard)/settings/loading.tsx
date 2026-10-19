export default function Loading() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-40 animate-pulse rounded-lg bg-ink-800/70" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-32 animate-pulse rounded-2xl bg-ink-900/70" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-2xl bg-ink-900/70" />
    </div>
  );
}
