"use client";

// The dental chart (6.11) — read a patient's mouth, mark teeth.
//
// The chart is append-only on the server: marking a tooth supersedes whatever it
// said before rather than overwriting it, so `GET` returns only current rows and
// the per-tooth history endpoint returns the trail. Nothing here deletes.

import { useCallback, useEffect, useState } from "react";

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// Request headers. Since 10.1 there is no authentication — the backend runs on
// this same machine and has no login — so this only sets the content type.
// Kept as a function (rather than inlined) so every call site stayed unchanged,
// and so re-adding a header later is a one-place edit.
function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export type ToothConditionName =
  | "caries"
  | "filled"
  | "crown"
  | "root_canal"
  | "missing"
  | "implant"
  | "bridge"
  | "impacted"
  | "fractured"
  | "mobile";

export const CONDITION_LABELS: Record<ToothConditionName, string> = {
  caries: "Caries",
  filled: "Filled",
  crown: "Crown",
  root_canal: "Root canal",
  missing: "Missing",
  implant: "Implant",
  bridge: "Bridge",
  impacted: "Impacted",
  fractured: "Fractured",
  mobile: "Mobile",
};

// Order shown in the picker and legend — roughly "most common first".
export const CONDITION_ORDER: ToothConditionName[] = [
  "caries",
  "filled",
  "root_canal",
  "crown",
  "missing",
  "bridge",
  "implant",
  "impacted",
  "fractured",
  "mobile",
];

// Colour per condition, from the design system's semantic tokens (6.2) — no new
// palette. Problems read danger/warning, restorations read good/primary, absent
// teeth read muted.
export const CONDITION_STYLES: Record<ToothConditionName, string> = {
  caries: "bg-danger text-danger-foreground border-danger",
  fractured: "bg-danger text-danger-foreground border-danger",
  mobile: "bg-warning text-warning-foreground border-warning",
  impacted: "bg-warning text-warning-foreground border-warning",
  filled: "bg-good text-good-foreground border-good",
  root_canal: "bg-primary text-primary-foreground border-primary",
  crown: "bg-secondary text-secondary-foreground border-secondary",
  bridge: "bg-secondary text-secondary-foreground border-secondary",
  implant: "bg-accent text-accent-foreground border-accent",
  missing: "bg-muted text-muted-foreground border-dashed",
};

export type ToothCondition = {
  id: string;
  tooth: string;
  condition: ToothConditionName;
  surfaces: string | null;
  note: string | null;
  recorded_visit_id: string | null;
  recorded_at: string;
  superseded_at: string | null;
};

export type ToothMark = {
  tooth: string;
  // null clears the tooth back to sound (superseding, never deleting).
  condition: ToothConditionName | null;
  surfaces?: string | null;
  note?: string | null;
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: ToothCondition[] }
  | { kind: "error"; message: string };

/** A patient's current chart. A tooth with no entry is sound. */
export function useChart(patientId: string): State & { refetch: () => void } {
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
        const headers = authHeaders();
        const res = await fetch(`${apiUrl}/patients/${patientId}/chart`, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as { items: ToothCondition[] };
        if (!cancelled) setState({ kind: "ready", items: data.items });
      } catch (error: unknown) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Could not load the chart.";
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

export type ChartResult =
  | { status: "ok"; items: ToothCondition[] }
  | { status: "forbidden" }
  | { status: "error"; message: string };

/**
 * Mark teeth. Partial — only the teeth listed change, so the rest of the chart
 * is left alone. Returns the whole current chart so the caller can re-render
 * without a second request.
 */
export async function markTeeth(
  patientId: string,
  entries: ToothMark[],
  visitId?: string | null,
): Promise<ChartResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();

    const res = await fetch(`${apiUrl}/patients/${patientId}/chart`, {
      method: "POST",
      headers,
      body: JSON.stringify({ entries, visit_id: visitId ?? null }),
    });
    if (res.ok) {
      const data = (await res.json()) as { items: ToothCondition[] };
      return { status: "ok", items: data.items };
    }
    if (res.status === 403) return { status: "forbidden" };
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not update the chart.",
    };
  }
}

/** Everything ever recorded for one tooth, oldest first. */
export async function toothHistory(
  patientId: string,
  tooth: string,
): Promise<ToothCondition[]> {
  if (!apiUrl) return [];
  const headers = authHeaders();
  if (!headers) return [];
  const res = await fetch(`${apiUrl}/patients/${patientId}/chart/${tooth}/history`, {
    headers,
  });
  if (!res.ok) return [];
  const data = (await res.json()) as { items: ToothCondition[] };
  return data.items;
}
