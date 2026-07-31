"use client";

// The dashboard worklists (6.8) — the "someone must act on this" queues that the
// end-to-end walkthrough found the app was quietly losing:
//
//   - unbilled visits   — treatment carried out but never billed (revenue gone)
//   - nothing recorded  — appointment marked done with no clinical write-up
//
// (The third queue, "open treatments with no follow-up booked", already had a UI
// from 4.8 — see app/needs-follow-up.tsx and lib/use-treatments.ts. Not
// duplicated here.)
//
// Both are read-only lists that link somewhere actionable, and each card hides
// itself when empty (the 6.6 lab-card pattern) so a quiet day stays quiet.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

async function authHeaders(): Promise<Record<string, string> | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

export type UnbilledVisit = {
  id: string;
  patient_id: string;
  patient_name: string;
  treatment_title: string;
  visit_date: string;
  dentist_name: string | null;
  procedure_count: number;
};

export type MissingVisitAppointment = {
  id: string;
  number: number;
  patient_id: string;
  patient_name: string;
  start_time: string;
  status: string;
  reason: string | null;
};

type State<T> =
  | { kind: "loading" }
  | { kind: "ready"; items: T[]; total: number }
  | { kind: "error"; message: string };

// One shared fetcher — the three worklists differ only by URL and payload shape.
function useList<T>(path: string, label: string): State<T> & { refetch: () => void } {
  const [state, setState] = useState<State<T>>(
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
        const headers = await authHeaders();
        if (!headers) throw new Error("Not signed in.");
        const res = await fetch(`${apiUrl}${path}`, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as { items: T[]; total?: number };
        if (!cancelled) {
          setState({
            kind: "ready",
            items: data.items ?? [],
            total: data.total ?? (data.items ?? []).length,
          });
        }
      } catch (error: unknown) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : `Could not load ${label}.`;
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [path, label, nonce]);

  return { ...state, refetch };
}

/** Visits with no invoice — the "to bill" queue. */
export function useUnbilledVisits() {
  return useList<UnbilledVisit>("/visits/unbilled", "unbilled visits");
}

/** Today's finished appointments with no visit recorded. */
export function useMissingVisits(today: string) {
  return useList<MissingVisitAppointment>(
    `/appointments?date=${today}&missing_visit=true`,
    "appointments",
  );
}

export type RecallDue = {
  id: string;
  name: string;
  phone: string | null;
  recall_due: string;
};

/**
 * Patients due a routine check-up — Phase 4 of the treatment workflow (6.10).
 *
 * A recall is a date on the patient meaning "this person should be booked",
 * which is repeat revenue a paper diary loses. `withinDays` widens the window
 * so the front desk can work a week ahead rather than only chasing the overdue.
 */
export function useRecallsDue(withinDays = 7) {
  return useList<RecallDue>(
    `/patients/recalls-due?within_days=${withinDays}`,
    "recalls",
  );
}
