import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-4 text-center">
      <p className="font-mono text-sm text-accent-300">404</p>
      <h1 className="text-xl font-semibold text-mist-100">Not found</h1>
      <p className="text-sm text-mist-400">That lead, dossier or draft does not exist.</p>
      <Link href="/leads" className="mt-2 text-sm text-accent-300 underline-offset-2 hover:underline">
        Back to leads
      </Link>
    </main>
  );
}
