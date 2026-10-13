import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, authEnabled, verifyToken } from "@/lib/auth";

/**
 * Optimistic access gate (Next 16 `proxy.ts`, replaces `middleware.ts`).
 *
 * This is a first line of defence only: pages/actions also call `requireSession()`.
 */
export function proxy(request: NextRequest) {
  if (!authEnabled()) return NextResponse.next();

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (verifyToken(token)) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  if (request.nextUrl.pathname !== "/") {
    url.searchParams.set("next", request.nextUrl.pathname);
  }
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|login).*)"],
};
