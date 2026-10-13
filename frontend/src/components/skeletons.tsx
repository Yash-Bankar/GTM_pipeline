import { SkeletonRows } from "@/components/ui";

export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-4">
      <div className="h-8 w-56 animate-pulse rounded-lg bg-ink-800/70" />
      <div className="rounded-2xl border border-ink-700/80 bg-ink-900/70">
        <SkeletonRows rows={rows} />
      </div>
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-9 w-64 animate-pulse rounded-lg bg-ink-800/70" />
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="rounded-2xl border border-ink-700/80 bg-ink-900/70">
          <SkeletonRows rows={8} />
        </div>
        <div className="h-72 animate-pulse rounded-2xl bg-ink-900/70" />
      </div>
    </div>
  );
}
