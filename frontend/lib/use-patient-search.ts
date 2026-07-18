"use client";

// Debounced patient search against the backend's GET /patients.
//
// Same authed browser-fetch pattern as use-current-staff.ts: getSession ->
// access_token -> fetch(NEXT_PUBLIC_API_URL/patients?...) with a Bearer header,
// through Caddy /api. The query is debounced so typing doesn't fire a request
// per keystroke.

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type PatientListItem = {
  id: string;
  name: string;
  phone: string | null;
  date_of_birth: string | null;
  age: number | null;
  gender: string | null;
  archived: boolean;
};

type Result = { items: PatientListItem[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;
const DEBOUNCE_MS = 300;

export function usePatientSearch(query: string): State {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    const timer = setTimeout(async () => {
      // Set loading here (inside the deferred callback), not synchronously in the
      // effect body — that trips react-hooks/set-state-in-effect.
      if (!cancelled) setState({ kind: "loading" });
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session) throw new Error("Not signed in.");

        const params = new URLSearchParams();
        const term = query.trim();
        if (term) params.set("q", term);

        const res = await fetch(`${apiUrl}/patients?${params.toString()}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Search failed (${res.status}).`);

        const data = (await res.json()) as Result;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Search failed.";
          setState({ kind: "error", message });
        }
      }
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return state;
}
