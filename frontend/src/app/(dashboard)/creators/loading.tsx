import { SkeletonRows } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-48 animate-pulse rounded-lg bg-ink-800/70" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-24 animate-pulse rounded-2xl bg-ink-900/70" />
        ))}
      </div>
      <div className="rounded-2xl border border-ink-700/80 bg-ink-900/70">
        <SkeletonRows rows={6} />
      </div>
    </div>
  );
}
