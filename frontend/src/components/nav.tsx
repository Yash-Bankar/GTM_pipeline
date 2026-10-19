"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logout } from "@/actions/auth";
import { cn } from "@/components/ui";

export const NAV_LINKS = [
  { href: "/leads", label: "Leads", glyph: "◎", hint: "Pipeline & enrichment" },
  { href: "/dossiers", label: "Dossiers", glyph: "❖", hint: "AI research" },
  { href: "/outreach", label: "Outreach", glyph: "✉", hint: "Draft review" },
  { href: "/settings", label: "Settings", glyph: "⚙", hint: "System health" },
];

export function Nav() {
  const pathname = usePathname();
  const LINKS = NAV_LINKS;

  return (
    <aside className="sticky top-5 hidden h-[calc(100dvh-2.5rem)] w-64 shrink-0 flex-col justify-between rounded-2xl border border-white/10 bg-ink-900/50 p-4 shadow-[0_8px_30px_rgba(0,0,0,0.35)] backdrop-blur-xl lg:flex">
      <div>
        <Link href="/leads" className="flex items-center gap-3 px-2 py-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-500/15 text-lg font-bold text-accent-300">
            S
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold text-mist-100">Synpo GTM</span>
            <span className="block font-mono text-[11px] text-mist-400">console v0.1</span>
          </span>
        </Link>

        <nav aria-label="Primary" className="mt-4 space-y-1">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400",
                  active
                    ? "bg-accent-500/12 text-accent-200 ring-1 ring-accent-600/40"
                    : "text-mist-300 hover:bg-ink-800 hover:text-mist-100",
                )}
              >
                <span aria-hidden className="w-4 text-center text-mist-400">
                  {link.glyph}
                </span>
                <span className="flex-1">
                  <span className="block font-medium">{link.label}</span>
                  <span className="block text-[11px] text-mist-400">{link.hint}</span>
                </span>
              </Link>
            );
          })}
        </nav>
      </div>

      <form action={logout}>
        <button
          type="submit"
          className="w-full rounded-xl border border-ink-700 px-3 py-2 text-left text-xs text-mist-400 transition-colors hover:border-rose-alert/40 hover:text-rose-alert"
        >
          Sign out
        </button>
      </form>
    </aside>
  );
}
