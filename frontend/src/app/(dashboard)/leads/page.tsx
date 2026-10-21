import { redirect } from "next/navigation";

/**
 * Legacy path.
 *
 * The review workspace is now "Creators" (PRD 6.1). The old path redirects
 * rather than 404s so saved links keep working; no content is deleted.
 */
export default function LeadsRedirect() {
  redirect("/creators");
}
