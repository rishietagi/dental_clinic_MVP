"use client";

// Patient profile — Overview (demographics + medical-notes banner), a "Record
// visit" action (4.4), a compact Treatments list with close/reopen (4.5), and a
// read-only visit history.
//
// The Treatments list here is deliberately compact — status + a Close/Reopen
// button. The richer tab (each treatment expandable to its nested visits) is
// 4.7. The visit history stays flat. Demographics remain read-only.

import { useState } from "react";
import Link from "next/link";

import { MedicalNotesBanner } from "@/components/medical-notes-banner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { usePatient } from "@/lib/use-patient";
import {
  closeTreatment,
  reopenTreatment,
  usePatientTreatments,
  type Treatment,
} from "@/lib/use-treatments";
import type { MutationResult } from "@/lib/use-treatment-items";
import { formatVisitDate, usePatientVisits, type Visit } from "@/lib/use-visits";

export function PatientProfile({ patientId }: { patientId: string }) {
  const state = usePatient(patientId);
  const staffState = useCurrentStaff();

  // Both live here so a lifecycle change (close/reopen) can refresh the visit
  // history too — a closed treatment changes the status shown against its
  // visits.
  const treatments = usePatientTreatments(patientId);
  const visits = usePatientVisits(patientId);

  const canManage =
    staffState.kind === "staff" &&
    (staffState.staff.roles.includes("dentist") ||
      staffState.staff.roles.includes("admin"));

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

      {/* Dentist-only, and hidden for an archived patient — recording a visit
          against someone archived is almost certainly a mistake. The API is the
          real guard either way. */}
      {canManage && !p.archived && (
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

      <TreatmentsSection
        state={treatments}
        canManage={canManage}
        onChanged={() => {
          treatments.refetch();
          visits.refetch();
        }}
      />

      <VisitHistory state={visits} />
    </div>
  );
}

// A compact treatments list with close/reopen. 4.7 turns this into the full
// tab with visits nested under each treatment.
function TreatmentsSection({
  state,
  canManage,
  onChanged,
}: {
  state: ReturnType<typeof usePatientTreatments>;
  canManage: boolean;
  onChanged: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Treatments</CardTitle>
      </CardHeader>
      <CardContent>
        {state.kind === "loading" && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {state.kind === "error" && (
          <p className="text-sm text-destructive">
            Couldn’t load treatments: {state.message}
          </p>
        )}
        {state.kind === "ready" && state.data.total === 0 && (
          <p className="text-sm text-muted-foreground">No treatments yet.</p>
        )}
        {state.kind === "ready" && state.data.total > 0 && (
          <ul className="flex flex-col divide-y">
            {state.data.items.map((t) => (
              <TreatmentRow
                key={t.id}
                treatment={t}
                canManage={canManage}
                onChanged={onChanged}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function TreatmentRow({
  treatment,
  canManage,
  onChanged,
}: {
  treatment: Treatment;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = treatment.status === "in_progress";

  async function act() {
    setBusy(true);
    setError(null);
    const result: MutationResult = open
      ? await closeTreatment(treatment.id)
      : await reopenTreatment(treatment.id);
    setBusy(false);

    if (result === "ok") {
      onChanged();
      return;
    }
    if (result === "forbidden") {
      setError("Only a dentist can change a treatment’s status.");
      return;
    }
    if (result === "conflict") {
      // Someone else changed it; refresh so the button reflects reality.
      setError("This treatment’s status just changed. Refreshing…");
      onChanged();
      return;
    }
    setError(result.error);
  }

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0">
      <span className="font-medium">{treatment.title}</span>
      {treatment.tooth_ref && (
        <span className="text-sm text-muted-foreground">
          tooth {treatment.tooth_ref}
        </span>
      )}
      <TreatmentStatus status={treatment.status} />
      {canManage && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="ml-auto"
          disabled={busy}
          onClick={act}
        >
          {busy ? "…" : open ? "Close" : "Reopen"}
        </Button>
      )}
      {error && (
        <p className="w-full text-xs text-destructive">{error}</p>
      )}
    </li>
  );
}

function VisitHistory({
  state,
}: {
  state: ReturnType<typeof usePatientVisits>;
}) {
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
