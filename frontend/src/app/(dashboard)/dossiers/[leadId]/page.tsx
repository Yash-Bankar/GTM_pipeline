import { redirect } from "next/navigation";

/**
 * Legacy path.
 *
 * The dossier and the evidence brief both live inside the creator detail view
 * now (PRD 6.1). This route redirects to that creator so saved links keep
 * working; the dossier data itself is not deleted.
 */
export default async function DossierDetailRedirect({
  params,
}: {
  params: Promise<{ leadId: string }>;
}) {
  const { leadId } = await params;
  redirect(`/creators/${leadId}`);
}
