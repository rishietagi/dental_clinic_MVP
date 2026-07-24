"use client";

// Fetches one day's appointments from GET /appointments?date=YYYY-MM-DD.
//
// Same authed browser->Caddy->backend pattern as use-patient-search.ts, but no
// debounce (the input is a date, not free typing) — it re-fetches whenever the
// `date` argument changes.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type AppointmentListItem = {
  id: string;
  patient_id: string;
  patient_name: string;
  dentist_id: string | null;
  dentist_name: string | null;
  consulting_dentist_id: string | null;
  consulting_dentist_name: string | null;
  treatment_id: string | null;
  start_time: string;
  duration_min: number;
  status: string;
  reason: string | null;
};

type Result = { items: AppointmentListItem[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// date is a YYYY-MM-DD string (what the API expects).
export function useDayAppointments(date: string): State & { refetch: () => void } {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  // Bumping this re-runs the effect (a manual refetch — e.g. after a status change).
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

        const res = await fetch(`${apiUrl}/appointments?date=${date}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as Result;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Could not load appointments.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [date, nonce]);

  return { ...state, refetch };
}
