"use client";

// Patient profile — Overview (demographics + medical-notes banner) plus, from
// 4.4, a "Record visit" action and a read-only visit history.
//
// The history here is deliberately flat (one row per visit, newest first). The
// richer Treatments tab — treatments expandable to their nested visits — is 4.7.
// Demographics remain read-only; there's still no edit/archive UI.

import Link from "next/link";

import { MedicalNotesBanner } from "@/components/medical-notes-banner";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { usePatient } from "@/lib/use-patient";
import { formatVisitDate, usePatientVisits, type Visit } from "@/lib/use-visits";

export function PatientProfile({ patientId }: { patientId: string }) {
  const state = usePatient(patientId);
  const staffState = useCurrentStaff();

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
  const canRecord =
    staffState.kind === "staff" &&
    (staffState.staff.roles.includes("dentist") ||
      staffState.staff.roles.includes("admin"));

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

      {/* Dentist-only, and hidden for an archived patient — recording a visit
          against someone archived is almost certainly a mistake. The API is the
          real guard either way. */}
      {canRecord && !p.archived && (
        <div>
          {/* Styled as a button but rendered as a real link (this Button is
              Base UI, which has no `asChild`; buttonVariants gives the look
              without nesting interactive elements). */}
          <Link
            href={`/patients/${patientId}/visits/new`}
            className={buttonVariants()}
          >
            Record visit
          </Link>
        </div>
      )}

      <VisitHistory patientId={patientId} />
    </div>
  );
}

function VisitHistory({ patientId }: { patientId: string }) {
  const state = usePatientVisits(patientId);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Visit history</CardTitle>
      </CardHeader>
      <CardContent>
        {state.kind === "loading" && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {state.kind === "error" && (
          <p className="text-sm text-destructive">
            Couldn’t load visits: {state.message}
          </p>
        )}
        {state.kind === "ready" && state.data.total === 0 && (
          <p className="text-sm text-muted-foreground">No visits recorded yet.</p>
        )}
        {state.kind === "ready" && state.data.total > 0 && (
          <ul className="flex flex-col divide-y">
            {state.data.items.map((v) => (
              <VisitRow key={v.id} visit={v} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function VisitRow({ visit }: { visit: Visit }) {
  const t = visit.treatment;
  return (
    <li className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="text-muted-foreground">
          {formatVisitDate(visit.visit_date)}
        </span>
        <span className="font-medium">{t.title}</span>
        {t.tooth_ref && (
          <span className="text-muted-foreground">tooth {t.tooth_ref}</span>
        )}
        <TreatmentStatus status={t.status} />
      </div>
      {visit.clinical_notes && (
        <p className="text-sm whitespace-pre-wrap">{visit.clinical_notes}</p>
      )}
      {visit.procedures.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {visit.procedures
            .map((p) => (p.tooth_ref ? `${p.treatment_item_name} (${p.tooth_ref})` : p.treatment_item_name))
            .join(" · ")}
        </p>
      )}
    </li>
  );
}

// The status belongs to the TREATMENT, not the visit — so every sitting on a
// finished thread reads "completed". That's correct: it describes the thread's
// current state, not what happened that day.
function TreatmentStatus({ status }: { status: string }) {
  const done = status === "completed";
  return (
    <span
      className={
        done
          ? "rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
          : "rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-800 dark:bg-blue-950 dark:text-blue-200"
      }
    >
      {done ? "completed" : "in progress"}
    </span>
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

function BackLink() {
  return (
    <Link href="/patients" className="text-sm text-muted-foreground hover:underline">
      ← Back to patients
    </Link>
  );
}
