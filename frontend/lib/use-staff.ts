"use client";

// Staff directory + management (6.3 reads, 6.5 writes). `useStaff` powers the
// dentist dropdowns; `useStaffList` + the mutations drive the Settings manage-staff
// section. Dentists here are name-only records (not logins) — see the API.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type StaffMember = {
  id: string;
  name: string;
  email: string;
  roles: string[];
  active: boolean;
  // What this dentist charges for a consultation (6.7). A decimal STRING, or
  // null when no fee has been set — which is not the same as "0". The visit
  // screen only offers a fee that has actually been set.
  consultation_fee: string | null;
};

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

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: StaffMember[] }
  | { kind: "error"; message: string };

// The dentist dropdown reader — active staff, optionally by role.
export function useStaff(role?: string): State {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      try {
        const headers = await authHeaders();
        if (!headers) throw new Error("Not signed in.");
        const url = new URL(`${apiUrl}/staff`);
        if (role) url.searchParams.set("role", role);
        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as { items: StaffMember[] };
        if (!cancelled) setState({ kind: "ready", items: data.items });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load staff.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [role]);

  return state;
}

// The Settings manage-staff list (includes inactive so they can be reactivated).
export function useStaffList(includeInactive = true): State & { refetch: () => void } {
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
        const url = new URL(`${apiUrl}/staff`);
        if (includeInactive) url.searchParams.set("include_inactive", "true");
        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as { items: StaffMember[] };
        if (!cancelled) setState({ kind: "ready", items: data.items });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load staff.";
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

export type StaffResult =
  | { status: "ok"; member: StaffMember }
  | { status: "forbidden" }
  | { status: "error"; message: string };

export async function createStaff(body: {
  name: string;
  email: string;
  roles?: string[];
}): Promise<StaffResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { status: "error", message: "Not signed in." };
    const res = await fetch(`${apiUrl}/staff`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (res.ok) return { status: "ok", member: (await res.json()) as StaffMember };
    if (res.status === 403) return { status: "forbidden" };
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
      message: error instanceof Error ? error.message : "Could not add the staff member.",
    };
  }
}

// Edit a staff record — in practice, set or clear a dentist's consultation fee.
//
// Pass `consultation_fee: null` to CLEAR it; omit the key entirely to leave it
// alone. The API distinguishes the two (exclude_unset), so the caller must not
// send an explicit null it didn't mean.
export async function updateStaff(
  id: string,
  changes: { name?: string; consultation_fee?: string | null },
): Promise<StaffResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { status: "error", message: "Not signed in." };
    const res = await fetch(`${apiUrl}/staff/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(changes),
    });
    if (res.ok) return { status: "ok", member: (await res.json()) as StaffMember };
    if (res.status === 403) return { status: "forbidden" };
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not update the fee.",
    };
  }
}

export async function setStaffActive(
  id: string,
  active: boolean,
): Promise<{ status: "ok" } | { status: "error"; message: string }> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { status: "error", message: "Not signed in." };
    const action = active ? "activate" : "deactivate";
    const res = await fetch(`${apiUrl}/staff/${id}/${action}`, { method: "POST", headers });
    if (res.ok) return { status: "ok" };
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not update the staff member.",
    };
  }
}
