"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { cn } from "@/components/ui";
import {
  SAVED_VIEWS,
  VIEW_HINTS,
  VIEW_LABELS,
  type SavedView,
} from "@/lib/views";

/**
 * Saved-view switcher.
 *
 * Views are links, so the current view is always reflected in the URL and the
 * browser's back button works. Each view carries its own count; the counts are
 * labelled per view rather than presented as a single additive funnel
 * (PRD 6.2).
 */
export function ViewSwitcher({
  active,
  counts,
}: {
  active: SavedView;
  counts: Record<string, number>;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function hrefFor(view: SavedView): string {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", view);
    params.delete("offset");
    const query = params.toString();
    return query ? `${pathname}?${query}` : pathname;
  }

  return (
    <div
      role="group"
      aria-label="Saved creator views"
      className="flex flex-wrap gap-1.5"
    >
      {SAVED_VIEWS.map((view) => {
        const isActive = view === active;
        const count = counts[view] ?? 0;
        return (
          <Link
            key={view}
            href={hrefFor(view)}
            aria-current={isActive ? "true" : undefined}
            title={VIEW_HINTS[view]}
            className={cn(
              "inline-flex min-h-11 items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400",
              isActive
                ? "border-accent-600/60 bg-accent-500/15 text-accent-200"
                : "border-ink-700 bg-ink-900/40 text-mist-300 hover:border-ink-600 hover:bg-ink-800 hover:text-mist-100",
            )}
          >
            {VIEW_LABELS[view]}
            <span
              className={cn(
                "rounded-full border px-1.5 py-px font-mono text-[10px]",
                isActive
                  ? "border-accent-600/50 text-accent-200"
                  : "border-ink-600 text-mist-400",
              )}
            >
              {count}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

/**
 * Live progress refresh.
 *
 * Pending states are refreshed on an interval so a queued/running job becomes
 * visible without a manual reload. The refresh is deliberately *non-disruptive*
 * (PRD 6.6 / QA V29):
 *
 * - it never moves focus: the focused element is captured before the refresh
 *   and restored afterwards, but only when the re-render actually dropped it;
 * - it never clears an unsaved edit: `router.refresh()` re-renders the server
 *   components in place, and the editors that hold unsaved text keep it in
 *   client state, so a poll cannot wipe a half-written draft;
 * - it announces completion **once**, not on every poll.
 */
export function LiveRefresh({
  pending,
  intervalMs = 5000,
}: {
  /** True while any visible state is still queued/running. */
  pending: boolean;
  intervalMs?: number;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const wasPendingRef = useRef(pending);
  // Focus to restore after the next render, if the poll dropped it.
  const focusTargetRef = useRef<string | null>(null);

  const refresh = useCallback(() => {
    // Capture the focused element so the refresh cannot move the user's focus.
    const active = document.activeElement as HTMLElement | null;
    focusTargetRef.current =
      active && active !== document.body && active.id ? active.id : null;

    startTransition(() => {
      router.refresh();
      setUpdatedAt(new Date().toLocaleTimeString());
    });
  }, [router]);

  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(refresh, intervalMs);
    return () => window.clearInterval(timer);
  }, [pending, intervalMs, refresh]);

  // Restore focus after the poll re-rendered the tree, but only when focus was
  // actually lost - never steal it back from where the user moved it.
  useEffect(() => {
    const id = focusTargetRef.current;
    if (!id) return;
    const active = document.activeElement as HTMLElement | null;
    if (active && active !== document.body) {
      // Focus is still on an element; the refresh did not drop it.
      focusTargetRef.current = null;
      return;
    }
    const element = document.getElementById(id);
    if (element) {
      element.focus({ preventScroll: true });
      focusTargetRef.current = null;
    }
  });

  // Announce the end of pending work once, not on every poll.
  useEffect(() => {
    if (wasPendingRef.current && !pending) {
      setAnnouncement("Pending work finished. The view is up to date.");
    }
    wasPendingRef.current = pending;
  }, [pending]);

  return (
    <>
      {pending ? (
        <div className="flex items-center gap-2 text-[11px] text-mist-400">
          <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-sky-400" />
          <span aria-hidden>
            {isPending
              ? "Refreshing..."
              : `Live · refreshing every ${Math.round(intervalMs / 1000)}s`}
            {updatedAt ? ` · last ${updatedAt}` : ""}
          </span>
        </div>
      ) : null}
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
    </>
  );
}
