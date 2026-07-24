"use client";

// Staff directory (step 6.3) — powers the dentist dropdowns on the booking and
// visit screens. Reads GET /staff (optionally ?role=dentist). Same authed fetch
// pattern as the other hooks.

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type StaffMember = {
  id: string;
  name: string;
  roles: string[];
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: StaffMember[] }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export function useStaff(role?: string): State {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session) throw new Error("Not signed in.");

        const url = new URL(`${apiUrl}/staff`);
        if (role) url.searchParams.set("role", role);

        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as { items: StaffMember[] };
        if (!cancelled) setState({ kind: "ready", items: data.items });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load staff.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [role]);

  return state;
}
