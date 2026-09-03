"use client";

// The lab vendor list (6.6) — the labs the clinic sends work to. Read by the
// "send to lab" picker; managed (add / deactivate) from Settings by an admin.
// Mirrors use-treatment-items: deactivate rather than delete, so old cases resolve.

import { useCallback, useEffect, useState } from "react";

export type LabVendor = {
  id: string;
  name: string;
  phone: string | null;
  address: string | null;
  active: boolean;
  created_at: string;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// Request headers. Since 10.1 there is no authentication — the backend runs on
// this same machine and has no login — so this only sets the content type.
// Kept as a function (rather than inlined) so every call site stayed unchanged,
// and so re-adding a header later is a one-place edit.
function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: LabVendor[] }
  | { kind: "error"; message: string };

export function useLabs(includeInactive = false): State & { refetch: () => void } {
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
        const url = new URL(`${apiUrl}/labs`);
        if (includeInactive) url.searchParams.set("include_inactive", "true");
        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);
        const data = (await res.json()) as { items: LabVendor[] };
        if (!cancelled) setState({ kind: "ready", items: data.items });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load labs.";
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

export type LabResult =
  | { status: "ok"; lab: LabVendor }
  | { status: "forbidden" }
  | { status: "error"; message: string };

export async function createLab(body: {
  name: string;
  phone?: string;
  address?: string;
}): Promise<LabResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();
    const res = await fetch(`${apiUrl}/labs`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (res.ok) return { status: "ok", lab: (await res.json()) as LabVendor };
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
      message: error instanceof Error ? error.message : "Could not add the lab.",
    };
  }
}

export async function setLabActive(
  id: string,
  active: boolean,
): Promise<{ status: "ok" } | { status: "error"; message: string }> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();
    const res = await fetch(`${apiUrl}/labs/${id}/${active ? "activate" : "deactivate"}`, {
      method: "POST",
      headers,
    });
    if (res.ok) return { status: "ok" };
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not update the lab.",
    };
  }
}
