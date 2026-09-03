"use client";

// Lab cases (6.6) — work sent out to a dental lab, and the dashboard lists that
// stop a case being forgotten.
//
// The readable numbers are the point of this feature: a case is "L-1042" and its
// appointment is "A-1007", because staff quote those to the lab on the phone. The
// `L-`/`A-` prefixes are presentation only (the DB stores plain integers).

import { useCallback, useEffect, useState } from "react";

export type SampleType =
  | "crown"
  | "bridge"
  | "denture_full"
  | "denture_partial"
  | "inlay_onlay"
  | "veneer"
  | "orthodontic"
  | "study_model"
  | "other";

export type LabCase = {
  id: string;
  number: number;
  patient_id: string;
  patient_name: string;
  lab_id: string;
  lab_name: string;
  visit_id: string | null;
  appointment_id: string | null;
  appointment_number: number | null;
  sample_type: string;
  tooth_ref: string | null;
  sent_date: string;
  expected_date: string | null;
  received_date: string | null;
  status: string;
  follow_up_done: boolean;
  notes: string | null;
  created_at: string;
};

export type LabDashboard = {
  overdue: LabCase[];
  due_soon: LabCase[];
  back_from_lab: LabCase[];
};

// Plain-English labels — the receptionist shouldn't meet snake_case.
export const SAMPLE_TYPE_LABELS: Record<string, string> = {
  crown: "Crown",
  bridge: "Bridge",
  denture_full: "Denture (full)",
  denture_partial: "Denture (partial)",
  inlay_onlay: "Inlay / Onlay",
  veneer: "Veneer",
  orthodontic: "Orthodontic appliance",
  study_model: "Study model",
  other: "Other",
};

export const SAMPLE_TYPES: SampleType[] = [
  "crown",
  "bridge",
  "denture_full",
  "denture_partial",
  "inlay_onlay",
  "veneer",
  "orthodontic",
  "study_model",
  "other",
];

export const LAB_STATUS_LABELS: Record<string, string> = {
  sent: "At the lab",
  received: "Back from lab",
  cancelled: "Cancelled",
};

export function sampleTypeLabel(t: string): string {
  return SAMPLE_TYPE_LABELS[t] ?? t;
}

export function labStatusLabel(s: string): string {
  return LAB_STATUS_LABELS[s] ?? s;
}

// "L-1042" / "A-1007" — the prefix is display only.
export function formatCaseNumber(n: number): string {
  return `L-${n}`;
}

export function formatApptNumber(n: number | null): string {
  return n === null ? "—" : `A-${n}`;
}

// Whole days from today until `iso` (negative = overdue). Dates are plain calendar
// dates, so this compares date parts only — no timezone drift.
export function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  const target = new Date(y, m - 1, d);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

// "3 days overdue" / "due tomorrow" / "due in 4 days" — the phrase the receptionist reads.
export function duePhrase(expected: string | null): string {
  const days = daysUntil(expected);
  if (days === null) return "no date";
  if (days < 0) return `${Math.abs(days)} ${Math.abs(days) === 1 ? "day" : "days"} overdue`;
  if (days === 0) return "due today";
  if (days === 1) return "due tomorrow";
  return `due in ${days} days`;
}

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// Request headers. Since 10.1 there is no authentication — the backend runs on
// this same machine and has no login — so this only sets the content type.
// Kept as a function (rather than inlined) so every call site stayed unchanged,
// and so re-adding a header later is a one-place edit.
function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

type ListState =
  | { kind: "loading" }
  | { kind: "ready"; items: LabCase[]; total: number }
  | { kind: "error"; message: string };

export function useLabCases(opts: { status?: string; patientId?: string } = {}): ListState & {
  refetch: () => void;
} {
  const { status, patientId } = opts;
  const [state, setState] = useState<ListState>(
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
        const headers = authHeaders();
        const url = new URL(`${apiUrl}/lab-cases`);
        if (status) url.searchParams.set("status", status);
        if (patientId) url.searchParams.set("patient_id", patientId);
        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as { items: LabCase[]; total: number };
        if (!cancelled) setState({ kind: "ready", items: data.items, total: data.total });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load lab cases.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [status, patientId, nonce]);

  return { ...state, refetch };
}

type DashState =
  | { kind: "loading" }
  | { kind: "ready"; data: LabDashboard }
  | { kind: "error"; message: string };

export function useLabDashboard(): DashState & { refetch: () => void } {
  const [state, setState] = useState<DashState>(
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
        const headers = authHeaders();
        const res = await fetch(`${apiUrl}/lab-cases/dashboard`, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as LabDashboard;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load lab work.";
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

export type LabCaseResult =
  | { status: "ok"; case: LabCase }
  | { status: "error"; message: string };

export async function createLabCase(body: {
  patient_id: string;
  lab_id: string;
  sample_type: string;
  sent_date: string;
  expected_date?: string | null;
  visit_id?: string | null;
  appointment_id?: string | null;
  tooth_ref?: string | null;
  notes?: string | null;
}): Promise<LabCaseResult> {
  return post(`${apiUrl}/lab-cases`, body);
}

export async function markReceived(id: string, receivedDate?: string): Promise<LabCaseResult> {
  return post(`${apiUrl}/lab-cases/${id}/received`, { received_date: receivedDate ?? null });
}

export async function cancelLabCase(id: string): Promise<LabCaseResult> {
  return post(`${apiUrl}/lab-cases/${id}/cancel`, undefined);
}

export async function dismissFollowUp(id: string, done = true): Promise<LabCaseResult> {
  return post(`${apiUrl}/lab-cases/${id}/follow-up-done`, { done });
}

async function post(url: string, body: unknown): Promise<LabCaseResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.ok) return { status: "ok", case: (await res.json()) as LabCase };
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") return { status: "error", message: data.detail };
    } catch {
      // fall through
    }
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Something went wrong.",
    };
  }
}
