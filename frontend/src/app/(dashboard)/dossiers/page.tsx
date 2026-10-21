import { redirect } from "next/navigation";

/**
 * Legacy path.
 *
 * Creator briefs live inside the creator detail view (PRD 6.1). The old
 * Dossiers route redirects to the creator workspace; no content is deleted and
 * the dossier data is still reachable from the creator detail page.
 */
export default function DossiersRedirect() {
  redirect("/creators");
}
