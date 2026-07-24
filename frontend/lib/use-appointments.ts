"use client";

// Booking an appointment from the browser (step 4.6).
//
// `POST /appointments` has existed since 3.2, but the calendar only ever
// *reschedules* (PATCH) existing appointments — bookings were seed-script only.
// This is the first appointment-CREATE path from the UI, added so the visit
// screen can book a follow-up in the same flow (BUILD_PLAN §3).
//
// The result mirrors the shared MutationResult so the caller can distinguish:
//   409 -> "conflict": the slot overlaps an existing appointment (same dentist)
//   404 -> the patient doesn't exist (shouldn't happen from the visit form)
// Double-booking is guaranteed by the DB's appointment_no_overlap constraint;
// this helper just surfaces the 409 the API already returns.

import { createClient } from "@/lib/supabase/client";
import type { MutationResult } from "@/lib/use-treatment-items";

export type AppointmentCreateBody = {
  patient_id: string;
  treatment_id?: string | null;
  dentist_id?: string | null;
  consulting_dentist_id?: string | null;
  start_time: string; // ISO 8601
  duration_min?: number;
  reason?: string | null;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export async function bookAppointment(
  body: AppointmentCreateBody,
): Promise<MutationResult> {
  if (!apiUrl) return { error: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) return { error: "Not signed in." };

    const res = await fetch(`${apiUrl}/appointments`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (res.ok) return "ok";
    if (res.status === 403) return "forbidden";
    if (res.status === 409) return "conflict";
    // 404 (patient) / 422 (validation) carry a useful detail from the API.
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") return { error: data.detail };
    } catch {
      // fall through
    }
    return { error: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      error: error instanceof Error ? error.message : "Could not book the appointment.",
    };
  }
}
