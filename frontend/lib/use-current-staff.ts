"use client";

// Fetches the local staff member (id, email, name, roles, active) from the
// backend's /me endpoint.
//
// Since 10.1 there is no authentication: the backend resolves the single local
// staff row itself (LOCAL_STAFF_ID), so this is a plain unauthenticated fetch.
// Roles still come back and still drive which nav items show — they are simply
// never used to REFUSE anything (see backend app/auth.py).

import { useEffect, useState } from "react";

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
        const res = await fetch(`${apiUrl}/me`);

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
