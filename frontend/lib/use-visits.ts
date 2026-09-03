"use client";

// Visits: a patient's history, and recording a new one.
//
// `recordVisit` posts the 4.3 POST /visits contract, whose defining rule is that
// the body carries EITHER `treatment_id` (continue an existing thread) OR a
// `treatment` stub (start a new one) — never both. The VisitCreateBody type below
// models that as a union so the form can't build an invalid request.
//
// The mutation result distinguishes the two failures the form can actually hit:
//   403 -> "forbidden": not a dentist/admin (writes are role-split on the API)
//   409 -> "conflict":  the chosen treatment is already completed
// Both are real outcomes here, so they get distinct messages rather than a
// generic "request failed".

import { useCallback, useEffect, useState } from "react";

export type ProcedureRead = {
  id: string;
  treatment_item_id: string;
  treatment_item_name: string;
  tooth_ref: string | null;
};

export type TreatmentSummary = {
  id: string;
  title: string;
  tooth_ref: string | null;
  status: string;
  phase: number | null;
  started_at: string;
  closed_at: string | null;
};

// What can be ordered under "Inv:" on the OPD card (6.10).
export type Investigation = "iopa" | "opg_conventional" | "opg_digital" | "other";

export const INVESTIGATION_LABELS: Record<Investigation, string> = {
  iopa: "IOPA",
  opg_conventional: "OPG (conventional)",
  opg_digital: "OPG (digital)",
  other: "Other",
};

/** The clinic's paper OPD card, field for field (6.10). All optional. */
export type ClinicalRecord = {
  history_note: string | null;
  bp_systolic: number | null;
  bp_diastolic: number | null;
  habits: string | null;
  extra_oral: string | null;
  intra_oral: string | null;
  soft_tissues: string | null;
  hard_tissue: string | null;
  occlusion: string | null;
  missing_teeth: string | null;
  other_findings: string | null;
  investigations: Investigation[];
  investigation_notes: string | null;
  provisional_diagnosis: string | null;
  differential_diagnosis: string | null;
  final_diagnosis: string | null;
  referred_to: string | null;
  referral_note: string | null;
};

export type Visit = ClinicalRecord & {
  id: string;
  // Human-readable OPD number, shown as V-1042.
  number: number;
  patient_id: string;
  treatment_id: string;
  appointment_id: string | null;
  dentist_id: string | null;
  dentist_name: string | null;
  consulting_dentist_id: string | null;
  consulting_dentist_name: string | null;
  visit_date: string;
  complaint: string | null;
  clinical_notes: string | null;
  created_at: string;
  updated_at: string;
  treatment: TreatmentSummary;
  procedures: ProcedureRead[];
};

/** Display helper — the visit's readable id, e.g. "V-1042". */
export function formatVisitNumber(n: number): string {
  return `V-${n}`;
}

export type ProcedureInput = {
  treatment_item_id: string;
  tooth_ref?: string | null;
};

// Exactly one of treatment_id / treatment — mirrors the API's model validator.
type TreatmentChoice =
  | { treatment_id: string; treatment?: never }
  | { treatment: { title: string; tooth_ref?: string | null }; treatment_id?: never };

export type VisitCreateBody = TreatmentChoice &
  Partial<ClinicalRecord> & {
    patient_id: string;
    appointment_id?: string | null;
    dentist_id?: string | null;
    consulting_dentist_id?: string | null;
    visit_date?: string | null;
    complaint?: string | null;
    clinical_notes?: string | null;
    procedures?: ProcedureInput[];
    treatment_status?: "in_progress" | "completed";
  };

type Result = { items: Visit[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// Request headers. Since 10.1 there is no authentication — the backend runs on
// this same machine and has no login — so this only sets the content type.
// Kept as a function (rather than inlined) so every call site stayed unchanged,
// and so re-adding a header later is a one-place edit.
function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export function usePatientVisits(
  patientId: string,
): State & { refetch: () => void } {
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
        const headers = authHeaders();

        const res = await fetch(`${apiUrl}/visits?patient_id=${patientId}`, {
          headers,
        });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as Result;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Could not load visits.";
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

// One visit by id (GET /visits/{id}), including its procedures + treatment. Used
// by the invoice-generate screen (5.4) to show what will be billed, and by the
// receipt to name the treatment/date. Same discriminated-state shape as usePatient.
type VisitState =
  | { kind: "loading" }
  | { kind: "ready"; visit: Visit }
  | { kind: "not-found" }
  | { kind: "error"; message: string };

export function useVisit(visitId: string): VisitState {
  const [state, setState] = useState<VisitState>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      try {
        const headers = authHeaders();

        const res = await fetch(`${apiUrl}/visits/${visitId}`, { headers });
        if (res.status === 404) {
          if (!cancelled) setState({ kind: "not-found" });
          return;
        }
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const visit = (await res.json()) as Visit;
        if (!cancelled) setState({ kind: "ready", visit });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load the visit.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [visitId]);

  return state;
}

// recordVisit returns the CREATED visit on success, not just "ok" — the inline
// follow-up (4.6) needs the visit's treatment_id, and a first visit auto-creates
// its treatment server-side, so the id isn't known until the response. The
// failure branches mirror MutationResult so callers handle 403/409/error the
// same way they do for other mutations.
export type RecordVisitResult =
  | { status: "ok"; visit: Visit }
  | { status: "forbidden" }
  | { status: "conflict" }
  | { status: "error"; message: string };

export async function recordVisit(
  body: VisitCreateBody,
): Promise<RecordVisitResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();

    const res = await fetch(`${apiUrl}/visits`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const visit = (await res.json()) as Visit;
      return { status: "ok", visit };
    }
    if (res.status === 403) return { status: "forbidden" };
    if (res.status === 409) return { status: "conflict" };
    // 404 (unknown treatment/catalogue item) and 422 (validation) carry a useful
    // `detail` from the API — surface it rather than a bare status code.
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") return { status: "error", message: data.detail };
    } catch {
      // fall through to the generic message
    }
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not record the visit.",
    };
  }
}

// Display helper: "2 Aug 2026" from an ISO timestamp. Local zone, consistent
// with the calendar screens (the clinic-timezone fix is still Phase 4 work).
export function formatVisitDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
