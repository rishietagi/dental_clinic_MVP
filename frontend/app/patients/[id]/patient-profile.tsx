"use client";

// Patient profile — Overview only (demographics + the medical-notes banner).
// Read-only this step; no edit/archive controls, no Treatments/Billing tabs yet.

import Link from "next/link";
import { TriangleAlert } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePatient, type Patient } from "@/lib/use-patient";

export function PatientProfile({ patientId }: { patientId: string }) {
  const state = usePatient(patientId);

  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.kind === "not-found") {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">Patient not found.</p>
        <BackLink />
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-destructive">Couldn’t load the patient: {state.message}</p>
        <BackLink />
      </div>
    );
  }

  const p = state.patient;

  return (
    <div className="flex flex-col gap-6">
      <BackLink />

      <MedicalNotesBanner notes={p.medical_notes} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {p.name}
            {p.archived && (
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">
                archived
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <Field label="Phone" value={p.phone} />
            <Field label="Age" value={p.age !== null ? `${p.age}` : null} />
            <Field label="Date of birth" value={p.date_of_birth} />
            <Field label="Gender" value={p.gender} />
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{value ?? "—"}</dd>
    </>
  );
}

// Renders ONLY when there are medical notes. The one diabetic / blood-thinner
// patient is exactly the case this exists for, so it's deliberately prominent.
function MedicalNotesBanner({ notes }: { notes: Patient["medical_notes"] }) {
  if (!notes || !notes.trim()) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    >
      <TriangleAlert className="mt-0.5 size-5 shrink-0" />
      <div>
        <p className="font-medium">Medical notes</p>
        <p className="whitespace-pre-wrap text-sm">{notes}</p>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/patients" className="text-sm text-muted-foreground hover:underline">
      ← Back to patients
    </Link>
  );
}
