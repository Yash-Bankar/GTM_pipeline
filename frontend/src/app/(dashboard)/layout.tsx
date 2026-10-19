import { Suspense, type ReactNode } from "react";

import { Nav } from "@/components/nav";
import { TopNav } from "@/components/top-nav";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto min-h-dvh w-full max-w-[1500px] px-4 py-5 lg:px-8">
      <Suspense fallback={null}>
        <TopNav />
      </Suspense>
      <div className="flex gap-6">
        <Suspense
          fallback={<div aria-hidden className="hidden w-64 shrink-0 rounded-2xl bg-ink-900/40 lg:block" />}
        >
          <Nav />
        </Suspense>
        <main className="min-w-0 flex-1 pb-16">{children}</main>
      </div>
    </div>
  );
}
