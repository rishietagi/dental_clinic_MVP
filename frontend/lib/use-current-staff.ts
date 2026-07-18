"use client";

// Fetches the signed-in staff member (id, email, name, roles, active) from the
// backend's /me endpoint. Roles come from OUR database, not the Supabase token,
// so they're always current.
//
// The call goes browser -> Caddy /api -> backend, exactly like health-card.tsx.
// We attach the Supabase access token as a Bearer header; the backend verifies
// it (ES256 via JWKS) and looks up the staff row.

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type CurrentStaff = {
  id: string;
  email: string;
  name: string;
  roles: string[];
  active: boolean;
};

type State =
  | { kind: "loading" }
  | { kind: "staff"; staff: CurrentStaff }
  | { kind: "not-staff" } // authenticated in Supabase but no active staff row (403)
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export function useCurrentStaff(): State {
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

        if (!session) {
          // The proxy guard normally prevents this, but handle it defensively.
          if (!cancelled) setState({ kind: "not-staff" });
          return;
        }

        const res = await fetch(`${apiUrl}/me`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });

        if (res.status === 403) {
          if (!cancelled) setState({ kind: "not-staff" });
          return;
        }
        if (!res.ok) {
          throw new Error(`/me returned ${res.status}`);
        }

        const staff = (await res.json()) as CurrentStaff;
        if (!cancelled) setState({ kind: "staff", staff });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load your profile.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
