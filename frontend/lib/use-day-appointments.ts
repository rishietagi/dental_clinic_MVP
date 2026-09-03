"use client";

// Fetches one day's appointments from GET /appointments?date=YYYY-MM-DD.
//
// Same authed browser->Caddy->backend pattern as use-patient-search.ts, but no
// debounce (the input is a date, not free typing) — it re-fetches whenever the
// `date` argument changes.

import { useCallback, useEffect, useState } from "react";

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
        const res = await fetch(`${apiUrl}/appointments?date=${date}`);
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

// One patient's whole appointment history, newest first (6.8).
//
// `GET /appointments?patient_id=` needs no date — which is the point: the
// profile asks "when are they next in / when were they last here" without
// knowing a date to look under. Before 6.8 this call 422'd, so the profile
// could not show either fact.
export function usePatientAppointments(
  patientId: string,
): State & { refetch: () => void } {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const res = await fetch(`${apiUrl}/appointments?patient_id=${patientId}`);
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
  }, [patientId, nonce]);

  return { ...state, refetch };
}
