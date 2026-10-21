"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logout } from "@/actions/auth";
import { NAV_LINKS } from "@/components/nav";
import { cn } from "@/components/ui";

/**
 * Compact top navigation shown below the `lg` breakpoint, where the sidebar is
 * hidden. Always visible (never hover-only) so navigation works at 360/768px.
 */
export function TopNav() {
  const pathname = usePathname();

  return (
    <div className="mb-4 lg:hidden">
      <div className="flex items-center justify-between gap-3">
        <Link href="/creators" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-500/15 text-sm font-bold text-accent-300">
            S
          </span>
          <span className="text-sm font-semibold text-mist-100">Synpo GTM</span>
        </Link>
        <form action={logout}>
          <button
            type="submit"
            className="min-h-11 rounded-lg border border-ink-700 px-3 text-xs text-mist-300 transition-colors hover:border-rose-alert/40 hover:text-rose-alert focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
          >
            Sign out
          </button>
        </form>
      </div>

      <nav
        aria-label="Primary"
        className="mt-3 flex gap-1 overflow-x-auto rounded-xl border border-white/10 bg-ink-900/50 p-1 backdrop-blur-xl"
      >
        {NAV_LINKS.map((link) => {
          const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-11 shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400",
                active
                  ? "bg-accent-500/12 text-accent-200 ring-1 ring-accent-600/40"
                  : "text-mist-300 hover:bg-ink-800 hover:text-mist-100",
              )}
            >
              <span aria-hidden className="text-mist-400">
                {link.glyph}
              </span>
              {link.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
