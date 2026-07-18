"use client";

// Sign-out control. Client component because signOut() runs in the browser and
// clears the session cookie there. After signing out we refresh + navigate to
// /login (the middleware would redirect anyway, but this is immediate).

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.refresh();
    router.push("/login");
  }

  return (
    <Button variant="outline" size="sm" onClick={handleSignOut}>
      Sign out
    </Button>
  );
}
