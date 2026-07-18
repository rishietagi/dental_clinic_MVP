// Supabase client for **browser** (client component) use.
//
// `createBrowserClient` from @supabase/ssr wires the auth session into cookies
// that the browser and the Next.js server both read, so a login here is visible
// to server components and middleware too. Used by the login form.
//
// Both values are NEXT_PUBLIC_* — they are inlined into the browser bundle at
// BUILD time and are safe to expose (the publishable/anon key is designed for
// the client; row-level security, added later, is what protects data).

import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
}
