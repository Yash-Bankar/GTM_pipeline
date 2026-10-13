import crypto from "node:crypto";

/** Session cookie name. */
export const SESSION_COOKIE = "synpo_session";

/** Whether the dashboard access gate is enabled (a password is configured). */
export function authEnabled(): boolean {
  return Boolean((process.env.DASHBOARD_PASSWORD ?? "").trim());
}

function secret(): string {
  return (
    (process.env.SESSION_SECRET ?? "").trim() ||
    (process.env.DASHBOARD_PASSWORD ?? "").trim()
  );
}

/** Deterministic HMAC token stored in the session cookie. */
export function expectedToken(): string {
  return crypto
    .createHmac("sha256", secret())
    .update("synpo-dashboard-session")
    .digest("hex");
}

function safeEqual(a: string, b: string): boolean {
  const bufferA = Buffer.from(a);
  const bufferB = Buffer.from(b);
  return bufferA.length === bufferB.length && crypto.timingSafeEqual(bufferA, bufferB);
}

/** Verify a session cookie token. */
export function verifyToken(token: string | undefined | null): boolean {
  if (!authEnabled()) return true;
  if (!token) return false;
  return safeEqual(token, expectedToken());
}

/** Constant-time password check for the login action. */
export function checkPassword(password: string): boolean {
  const expected = (process.env.DASHBOARD_PASSWORD ?? "").trim();
  if (!expected) return true;
  return safeEqual(password ?? "", expected);
}
