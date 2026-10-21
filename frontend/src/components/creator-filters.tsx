import Link from "next/link";

const STATUS_OPTIONS = ["", "needs_data", "queued", "running", "complete", "blocked"];
const SORT_OPTIONS = [
  { value: "", label: "Default order" },
  { value: "oldest", label: "Oldest first" },
  { value: "newest", label: "Newest first" },
];

/**
 * Search, research-state filter and sort.
 *
 * The saved view is carried through the form as a hidden field so applying a
 * filter never loses the operator's place in the review queue.
 */
export function CreatorFilters({
  q,
  status,
  view,
  sort,
}: {
  q?: string;
  status?: string;
  view: string;
  sort?: string;
}) {
  return (
    <form method="get" action="/creators" className="flex flex-wrap items-end gap-2">
      <input type="hidden" name="view" value={view} />
      {sort ? <input type="hidden" name="sort" value={sort} /> : null}

      <div className="min-w-0 flex-1 sm:w-64 sm:flex-none">
        <label
          htmlFor="creator-search"
          className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-mist-400"
        >
          Search creators
        </label>
        <input
          id="creator-search"
          name="q"
          defaultValue={q ?? ""}
          placeholder="Username, name or bio"
          className="field"
        />
      </div>

      <div className="w-full sm:w-44">
        <label
          htmlFor="creator-status"
          className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-mist-400"
        >
          Research state
        </label>
        <select id="creator-status" name="status" defaultValue={status ?? ""} className="field">
          {STATUS_OPTIONS.map((option) => (
            <option key={option || "all"} value={option}>
              {option ? option.replace(/_/g, " ") : "Any research state"}
            </option>
          ))}
        </select>
      </div>

      <div className="w-full sm:w-40">
        <label
          htmlFor="creator-sort"
          className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-mist-400"
        >
          Sort
        </label>
        <select id="creator-sort" name="sort" defaultValue={sort ?? ""} className="field">
          {SORT_OPTIONS.map((option) => (
            <option key={option.value || "default"} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        className="min-h-11 rounded-lg border border-ink-600 px-4 py-2 text-sm font-semibold text-mist-200 transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
      >
        Apply filters
      </button>

      {q || status ? (
        <Link
          href={`/creators?view=${encodeURIComponent(view)}`}
          className="min-h-11 py-2 text-xs text-mist-400 underline-offset-2 hover:text-mist-200 hover:underline"
        >
          Clear filters
        </Link>
      ) : null}
    </form>
  );
}
