// Supabase client for **server** (server component / route handler) use.
//
// Unlike the browser client, this one has no direct access to document.cookie,
// so it is handed Next's cookie store to read and write through. Session cookies
// therefore stay in sync between server and browser.
//
// Note the try/catch around setAll: a Server Component render is allowed to READ
// cookies but not WRITE them. In that context the write is safely ignored — the
// middleware (which CAN write cookies) is what actually refreshes the session.

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component, which can't set cookies.
            // The middleware refreshes the session, so this is safe to ignore.
          }
        },
      },
    },
  );
}
