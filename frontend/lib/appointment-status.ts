"use client";

// Shared appointment-status helpers for the calendar views (step 3.5): display
// labels, colour styles, the legal-next-status map, and the change-status call.
//
// The NEXT_STATUSES map mirrors the backend state machine
// (app/services/appointments.py) so the UI only offers legal buttons — but the
// API is the real guard (an illegal POST returns 409 regardless of the UI).

export const STATUSES = ["booked", "arrived", "done", "cancelled", "no_show"] as const;
export type Status = (typeof STATUSES)[number];

export const STATUS_LABELS: Record<Status, string> = {
  booked: "Booked",
  arrived: "Arrived",
  done: "Done",
  cancelled: "Cancelled",
  no_show: "No-show",
};

// Plain, readable colour pills (light/dark aware via Tailwind tokens). Real
// visual design is Phase 6; colour-by-status is the one bit of colour asked for
// now. Cancelled reads as muted; no-show as a warning.
export const STATUS_STYLES: Record<Status, string> = {
  booked: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  arrived: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  done: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200",
  cancelled: "bg-muted text-muted-foreground line-through",
  no_show: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

// Legal next transitions — kept in sync with the backend _ALLOWED map.
export const NEXT_STATUSES: Record<Status, Status[]> = {
  booked: ["arrived", "cancelled", "no_show"],
  arrived: ["done", "cancelled", "no_show"],
  done: [],
  cancelled: [],
  no_show: [],
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as Status] ?? status;
}

export function statusStyle(status: string): string {
  return STATUS_STYLES[status as Status] ?? "bg-muted text-muted-foreground";
}

export function nextStatuses(status: string): Status[] {
  return NEXT_STATUSES[status as Status] ?? [];
}

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// POST /appointments/{id}/status. Returns "ok" | "conflict" (illegal transition,
// e.g. another PC already moved it) | an error, so callers can react + refetch.
export async function changeStatus(
  id: string,
  status: Status,
): Promise<"ok" | "conflict" | { error: string }> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const res = await fetch(`${apiUrl}/appointments/${id}/status`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status }),
    });
    if (res.status === 409) return "conflict";
    if (!res.ok) return { error: `Status change failed (${res.status}).` };
    return "ok";
  } catch (error: unknown) {
    return { error: error instanceof Error ? error.message : "Status change failed." };
  }
}
