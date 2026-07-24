"use client";

// Creating a patient from the browser (step 6.3). `POST /patients` has existed
// since 2.2, but there was no UI for it — the app had no "Add patient" button.
// Any active staff may register a patient.

import { createClient } from "@/lib/supabase/client";

export type PatientCreateBody = {
  name: string;
  phone?: string | null;
  date_of_birth?: string | null; // YYYY-MM-DD
  gender?: string | null;
  medical_notes?: string | null;
};

export type CreatePatientResult =
  | { status: "ok"; id: string }
  | { status: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export async function createPatient(
  body: PatientCreateBody,
): Promise<CreatePatientResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) return { status: "error", message: "Not signed in." };

    const res = await fetch(`${apiUrl}/patients`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const data = (await res.json()) as { id: string };
      return { status: "ok", id: data.id };
    }
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
      message: error instanceof Error ? error.message : "Could not create the patient.",
    };
  }
}
