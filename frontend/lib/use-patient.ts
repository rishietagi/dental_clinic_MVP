"use client";

// Fetches one patient by id from GET /patients/{id}. Same authed browser->Caddy
// ->backend pattern as use-patient-search, but a single record and no debounce.
// Returns the FULL record including medical_notes (only the single-patient
// endpoint returns that — the list omits it).

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type Patient = {
  id: string;
  name: string;
  phone: string | null;
  date_of_birth: string | null;
  age: number | null;
  gender: string | null;
  medical_notes: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; patient: Patient }
  | { kind: "not-found" }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export function usePatient(patientId: string): State {
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

        const res = await fetch(`${apiUrl}/patients/${patientId}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });

        if (res.status === 404) {
          if (!cancelled) setState({ kind: "not-found" });
          return;
        }
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const patient = (await res.json()) as Patient;
        if (!cancelled) setState({ kind: "ready", patient });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load the patient.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [patientId]);

  return state;
}
