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
import type { MutationResult } from "@/lib/use-treatment-items";

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

// --- lifecycle (step 4.5): close / reopen -----------------------------------
//
// Writes are dentist/admin on the API, so the result distinguishes:
//   403 -> "forbidden": not a dentist
//   409 -> "conflict":  the treatment is already in the target state (e.g. a
//                       stale button after someone else changed it)
// The caller shows each distinctly and refetches on conflict.

async function transition(
  treatmentId: string,
  action: "close" | "reopen",
): Promise<MutationResult> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) return { error: "Not signed in." };

    const res = await fetch(`${apiUrl}/treatments/${treatmentId}/${action}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.access_token}` },
    });

    if (res.ok) return "ok";
    if (res.status === 403) return "forbidden";
    if (res.status === 409) return "conflict";
    return { error: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      error: error instanceof Error ? error.message : `Could not ${action} the treatment.`,
    };
  }
}

export function closeTreatment(id: string): Promise<MutationResult> {
  return transition(id, "close");
}

export function reopenTreatment(id: string): Promise<MutationResult> {
  return transition(id, "reopen");
}

// --- needs-follow-up report (step 4.8) --------------------------------------
//
// Clinic-wide: open treatments with no upcoming appointment — "revenue walking
// out the door" (BUILD_PLAN §3). Feeds the dashboard section. Same fetch shape
// as usePatientTreatments, but no patient arg.

export type TreatmentNeedsFollowUp = {
  id: string;
  patient_id: string;
  patient_name: string;
  title: string;
  tooth_ref: string | null;
  started_at: string;
  last_visit_date: string | null;
};

type NeedsFollowUpResult = { items: TreatmentNeedsFollowUp[]; total: number };

type NeedsFollowUpState =
  | { kind: "loading" }
  | { kind: "ready"; data: NeedsFollowUpResult }
  | { kind: "error"; message: string };

export function useNeedsFollowUp(): NeedsFollowUpState & { refetch: () => void } {
  const [state, setState] = useState<NeedsFollowUpState>(
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

        const res = await fetch(`${apiUrl}/treatments/needs-follow-up`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as NeedsFollowUpResult;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Could not load the report.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [nonce]);

  return { ...state, refetch };
}
