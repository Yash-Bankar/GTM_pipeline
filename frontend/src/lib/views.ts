/** Saved creator views for the review workspace (V2-08). */

/** The saved views offered on the Creators page, in display order. */
export const SAVED_VIEWS = [
  "to_review",
  "all",
  "research_more",
  "shortlisted",
  "rejected",
  "attention",
] as const;

export type SavedView = (typeof SAVED_VIEWS)[number];

export const DEFAULT_VIEW: SavedView = "to_review";

/** Human labels for the view switcher. */
export const VIEW_LABELS: Record<SavedView, string> = {
  to_review: "To review",
  all: "All creators",
  research_more: "Research more",
  shortlisted: "Shortlisted",
  rejected: "Rejected",
  attention: "Needs attention",
};

/** Short descriptions shown under the view switcher. */
export const VIEW_HINTS: Record<SavedView, string> = {
  to_review: "Not reviewed, plus shortlisters whose evidence changed. Rejected creators are excluded.",
  all: "Every captured creator, including rejected and blocked ones.",
  research_more: "Creators an operator asked for more research on.",
  shortlisted: "Creators on a current shortlist, whatever their decision currency.",
  rejected: "Rejected creators, kept for deduplication and history.",
  attention: "Blocked system work that needs a remedy.",
};

export function normalizeView(view: string | null | undefined): SavedView {
  const value = (view ?? "").trim().toLowerCase();
  return (SAVED_VIEWS as readonly string[]).includes(value)
    ? (value as SavedView)
    : DEFAULT_VIEW;
}

export function isSavedView(view: string | null | undefined): view is SavedView {
  return (SAVED_VIEWS as readonly string[]).includes((view ?? "").trim().toLowerCase());
}
