"use client";

// Fetches a week's appointments from GET /appointments?from=<mon>&to=<sun>.
//
// Same authed browser->Caddy->backend pattern as use-day-appointments.ts, over a
// date RANGE instead of a single day. Exposes refetch() so a successful drag-drop
// reschedule can refresh the grid.

import { useCallback, useEffect, useState } from "react";

import type { AppointmentListItem } from "@/lib/use-day-appointments";
import { weekDays } from "@/lib/week";

type Result = { items: AppointmentListItem[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// weekStart is the Monday (YYYY-MM-DD) of the week to load.
export function useWeekAppointments(weekStart: string): State & { refetch: () => void } {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  // Bumping this forces the effect to re-run (a manual refetch).
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const days = weekDays(weekStart);
        const from = days[0];
        const to = days[days.length - 1];

        const res = await fetch(`${apiUrl}/appointments?from=${from}&to=${to}`);
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
  }, [weekStart, nonce]);

  return { ...state, refetch };
}

// Reschedule an appointment's start_time via PATCH. Returns "ok" | "conflict" |
// an error message, so the caller can show the 409 inline and revert.
export async function rescheduleAppointment(
  id: string,
  startTimeIso: string,
): Promise<"ok" | "conflict" | { error: string }> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const res = await fetch(`${apiUrl}/appointments/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ start_time: startTimeIso }),
    });
    if (res.status === 409) return "conflict";
    if (!res.ok) return { error: `Reschedule failed (${res.status}).` };
    return "ok";
  } catch (error: unknown) {
    return { error: error instanceof Error ? error.message : "Reschedule failed." };
  }
}
