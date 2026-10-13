import { SkeletonRows } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-4">
      <div className="h-9 w-64 animate-pulse rounded-lg bg-ink-800/70" />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="rounded-2xl border border-ink-700/80 bg-ink-900/70">
          <SkeletonRows rows={8} />
        </div>
        <div className="h-72 animate-pulse rounded-2xl bg-ink-900/70" />
      </div>
    </div>
  );
}
