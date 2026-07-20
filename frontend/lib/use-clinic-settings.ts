"use client";

// Clinic settings (step 4.9): hours, slot size, timezone.
//
// Read by the calendar (grid rows), the dashboard/day-view ("today" and time
// rendering in the clinic zone), and the visit form (follow-up duration). Edited
// by an admin via the settings screen.
//
// The hook always RESOLVES to a value: while loading it returns the previous
// hardcoded defaults (9-18 / 30 min / Asia/Kolkata) so no screen ever renders an
// empty grid or crashes on a missing timezone. Callers can treat `settings` as
// always-present and use `loading`/`error` only for messaging.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";
import type { MutationResult } from "@/lib/use-treatment-items";

export type ClinicSettings = {
  open_hour: number;
  close_hour: number;
  slot_minutes: number;
  timezone: string;
};

// The historical hardcoded values — the fallback until the fetch resolves.
export const DEFAULT_CLINIC_SETTINGS: ClinicSettings = {
  open_hour: 9,
  close_hour: 18,
  slot_minutes: 30,
  timezone: "Asia/Kolkata",
};

type State = "loading" | "ready" | "error";

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export function useClinicSettings(): {
  settings: ClinicSettings;
  state: State;
  message: string | null;
  refetch: () => void;
} {
  const [settings, setSettings] = useState<ClinicSettings>(DEFAULT_CLINIC_SETTINGS);
  const [state, setState] = useState<State>(apiUrl ? "loading" : "error");
  const [message, setMessage] = useState<string | null>(
    apiUrl ? null : "NEXT_PUBLIC_API_URL is not set.",
  );
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

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

        const res = await fetch(`${apiUrl}/clinic-settings`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as ClinicSettings;
        if (!cancelled) {
          setSettings(data);
          setState("ready");
        }
      } catch (error: unknown) {
        if (!cancelled) {
          // Keep the default settings usable; only surface the message.
          setState("error");
          setMessage(
            error instanceof Error ? error.message : "Could not load clinic settings.",
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [nonce]);

  return { settings, state, message, refetch };
}

export async function updateClinicSettings(
  changes: Partial<ClinicSettings>,
): Promise<MutationResult> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) return { error: "Not signed in." };

    const res = await fetch(`${apiUrl}/clinic-settings`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(changes),
    });

    if (res.ok) return "ok";
    if (res.status === 403) return "forbidden";
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") return { error: data.detail };
    } catch {
      // fall through
    }
    return { error: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      error: error instanceof Error ? error.message : "Could not save settings.",
    };
  }
}
