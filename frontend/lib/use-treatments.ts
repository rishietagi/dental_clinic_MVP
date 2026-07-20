"use client";

// A patient's treatments (the threads that tie visits together).
//
// Same authed browser->Caddy->backend pattern as the other hooks. Read-only:
// treatments are CREATED by POST /visits (the 4.3 auto-create rule) and their
// lifecycle (close/reopen) is step 4.5 — there are no write helpers here yet.
//
// The API returns open treatments first, so the visit form's "continue this
// treatment" picker gets actionable threads at the top without re-sorting.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type Treatment = {
  id: string;
  patient_id: string;
  title: string;
  tooth_ref: string | null;
  status: string;
  started_at: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
};

type Result = { items: Treatment[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export function usePatientTreatments(
  patientId: string,
  options: { openOnly?: boolean } = {},
): State & { refetch: () => void } {
  const { openOnly = false } = options;
  const [state, setState] = useState<State>(
    apiUrl
      ? { kind: "loading" }
      : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session) throw new Error("Not signed in.");

        const query = new URLSearchParams({ patient_id: patientId });
        if (openOnly) query.set("status", "in_progress");

        const res = await fetch(`${apiUrl}/treatments?${query}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as Result;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Could not load treatments.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [patientId, openOnly, nonce]);

  return { ...state, refetch };
}
