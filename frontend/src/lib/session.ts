import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { SESSION_COOKIE, authEnabled, verifyToken } from "./auth";

/** True when the request carries a valid session (or the gate is disabled). */
export async function isAuthenticated(): Promise<boolean> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return verifyToken(token);
}

/** Redirect to /login when the access gate is enabled and the session is invalid. */
export async function requireSession(): Promise<void> {
  if (!authEnabled()) return;
  if (!(await isAuthenticated())) redirect("/login");
}
