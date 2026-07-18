// Session refresh + route guard, run from the root middleware on every request.
//
// Two jobs:
//  1. Refresh the auth token. Server Components can't write cookies, so the
//     middleware calls getUser() (which refreshes an expired token) and writes
//     the fresh cookies onto both the request (for this render) and the response
//     (for the browser). This is why a signed-in user stays signed in on reload.
//  2. Guard routes. No user and not already on /login  -> redirect to /login.
//     Signed-in user visiting /login                   -> redirect to home.
//
// Follows Supabase's official @supabase/ssr pattern: the supabaseResponse object
// must be returned (or its cookies copied onto a redirect) so the refreshed
// session cookies actually reach the browser.

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // IMPORTANT: getUser() must be called right after creating the client and
  // before any other logic — it is what triggers the token refresh.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isLoginRoute = pathname === "/login";

  // Not signed in and heading anywhere but the login page -> send to login.
  if (!user && !isLoginRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    const redirect = NextResponse.redirect(url);
    // Carry over any refreshed cookies so the response stays consistent.
    supabaseResponse.cookies.getAll().forEach((cookie) =>
      redirect.cookies.set(cookie),
    );
    return redirect;
  }

  // Already signed in but sitting on /login -> send to home.
  if (user && isLoginRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    const redirect = NextResponse.redirect(url);
    supabaseResponse.cookies.getAll().forEach((cookie) =>
      redirect.cookies.set(cookie),
    );
    return redirect;
  }

  return supabaseResponse;
}
