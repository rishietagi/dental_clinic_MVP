// Root proxy (Next.js 16 renamed the "middleware" convention to "proxy" — same
// API, clearer name). Runs on every matched request before the page renders.
// Delegates to updateSession, which refreshes the Supabase session and applies
// the signed-in / signed-out redirect guard.

import { type NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

export async function proxy(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    // Run on all paths EXCEPT Next internals and static asset files. Auth cookies
    // aren't needed for those, and skipping them keeps every asset request cheap.
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
