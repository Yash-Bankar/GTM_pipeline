import Link from "next/link";

const STATUS_OPTIONS = ["", "needs_data", "queued", "running", "complete", "blocked"];

export function LeadFilters({ q, status }: { q?: string; status?: string }) {
  return (
    <form method="get" action="/leads" className="flex flex-wrap items-center gap-2">
      <input
        name="q"
        defaultValue={q ?? ""}
        placeholder="Search username, name, bio…"
        className="field sm:w-72"
        aria-label="Search leads"
      />
      <select name="status" defaultValue={status ?? ""} className="field sm:w-44" aria-label="Filter by progress">
        {STATUS_OPTIONS.map((option) => (
          <option key={option || "all"} value={option}>
            {option ? option.replace(/_/g, " ") : "All progress"}
          </option>
        ))}
      </select>
      <button
        type="submit"
        className="rounded-lg border border-ink-600 px-4 py-2 text-sm font-semibold text-mist-200 transition-colors hover:bg-ink-800"
      >
        Filter
      </button>
      {(q || status) && (
        <Link href="/leads" className="text-xs text-mist-400 underline-offset-2 hover:text-mist-200 hover:underline">
          Clear
        </Link>
      )}
    </form>
  );
}
