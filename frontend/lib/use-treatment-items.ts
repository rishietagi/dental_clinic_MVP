"use client";

// The treatment catalogue: load + mutate.
//
// Same authed browser->Caddy->backend pattern as the appointment hooks, with the
// refetch nonce. Reads work for any staff; writes are admin-only on the API, so
// the mutation helpers distinguish "forbidden" (403 — not an admin) from
// "conflict" (409 — duplicate name) and let the caller show each properly.
//
// Prices cross the wire as strings so the exact decimal survives (the column is
// Numeric(10,2)); never parse them into a float for arithmetic.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type TreatmentItem = {
  id: string;
  name: string;
  default_price: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

type Result = { items: TreatmentItem[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

export type MutationResult = "ok" | "forbidden" | "conflict" | { error: string };

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

// Maps a mutation response to the shared result shape.
function classify(res: Response): MutationResult {
  if (res.ok) return "ok";
  if (res.status === 403) return "forbidden";
  if (res.status === 409) return "conflict";
  return { error: `Request failed (${res.status}).` };
}

export function useTreatmentItems(
  includeInactive: boolean,
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
        const headers = await authHeaders();
        if (!headers) throw new Error("Not signed in.");

        const res = await fetch(
          `${apiUrl}/treatment-items?include_inactive=${includeInactive}`,
          { headers },
        );
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
  }, [includeInactive, nonce]);

  return { ...state, refetch };
}

export async function createItem(
  name: string,
  defaultPrice: string,
): Promise<MutationResult> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { error: "Not signed in." };
    const res = await fetch(`${apiUrl}/treatment-items`, {
      method: "POST",
      headers,
      body: JSON.stringify({ name, default_price: defaultPrice }),
    });
    return classify(res);
  } catch (error: unknown) {
    return { error: error instanceof Error ? error.message : "Create failed." };
  }
}

export async function updateItem(
  id: string,
  changes: { name?: string; default_price?: string },
): Promise<MutationResult> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { error: "Not signed in." };
    const res = await fetch(`${apiUrl}/treatment-items/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(changes),
    });
    return classify(res);
  } catch (error: unknown) {
    return { error: error instanceof Error ? error.message : "Update failed." };
  }
}

export async function setItemActive(
  id: string,
  active: boolean,
): Promise<MutationResult> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { error: "Not signed in." };
    const res = await fetch(
      `${apiUrl}/treatment-items/${id}/${active ? "activate" : "deactivate"}`,
      { method: "POST", headers },
    );
    return classify(res);
  } catch (error: unknown) {
    return { error: error instanceof Error ? error.message : "Update failed." };
  }
}

// Display helper — formats the decimal string as rupees without doing float math.
export function formatPrice(value: string): string {
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(num);
}
