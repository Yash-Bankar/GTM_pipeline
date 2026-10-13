import { Suspense, type ReactNode } from "react";

import { Nav } from "@/components/nav";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[1500px] gap-6 px-4 py-5 lg:px-8">
      <Suspense
        fallback={<div aria-hidden className="hidden w-64 shrink-0 rounded-2xl bg-ink-900/40 lg:block" />}
      >
        <Nav />
      </Suspense>
      <main className="min-w-0 flex-1 pb-16">{children}</main>
    </div>
  );
}
