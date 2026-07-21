"use client";

// Patient profile — Overview (demographics + medical-notes banner), a "Record
// visit" action (4.4), and the Treatments section (4.5 close/reopen + 4.7 nested
// visits).
//
// The clinical model threads visits under a treatment (BUILD_PLAN §3), so the
// profile shows exactly that: one Treatments section, each treatment expandable
// to its own sittings. There is no separate flat visit-history card any more —
// it was merged in here so a visit shows once, under the thread it belongs to.
// Demographics remain read-only.

import { useState } from "react";
import Link from "next/link";

import { MedicalNotesBanner } from "@/components/medical-notes-banner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { statusLabel, useVisitInvoice } from "@/lib/use-invoices";
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
        treatmentsState={treatments}
        visitsState={visits}
        canManage={canManage}
        onChanged={() => {
          treatments.refetch();
          visits.refetch();
        }}
      />
    </div>
  );
}

// The Treatments section: one card, each treatment expandable to its visits.
// This is the shape the clinical model implies (BUILD_PLAN §3, §7) — a treatment
// and its sittings shown together, not two disconnected lists.
//
// Visits are grouped under their treatment CLIENT-SIDE: GET /visits?patient_id=
// already returns every visit carrying treatment_id (newest first), so no nested
// endpoint is needed.
function TreatmentsSection({
  treatmentsState,
  visitsState,
  canManage,
  onChanged,
}: {
  treatmentsState: ReturnType<typeof usePatientTreatments>;
  visitsState: ReturnType<typeof usePatientVisits>;
  canManage: boolean;
  onChanged: () => void;
}) {
  // Bucket visits by treatment. Insertion order preserves the hook's newest-
  // first ordering within each treatment.
  const visitsByTreatment = new Map<string, Visit[]>();
  if (visitsState.kind === "ready") {
    for (const v of visitsState.data.items) {
      const bucket = visitsByTreatment.get(v.treatment_id);
      if (bucket) bucket.push(v);
      else visitsByTreatment.set(v.treatment_id, [v]);
    }
    if (treatmentsState.kind === "ready" && process.env.NODE_ENV !== "production") {
      const known = new Set(treatmentsState.data.items.map((t) => t.id));
      for (const tid of visitsByTreatment.keys()) {
        if (!known.has(tid)) {
          // Shouldn't happen — every visit has a treatment, and the list is
          // unfiltered. Flag it in dev rather than dropping the visit silently.
          console.warn(`Visit references unknown treatment ${tid}`);
        }
      }
    }
  }

  const loading =
    treatmentsState.kind === "loading" || visitsState.kind === "loading";
  const errored =
    treatmentsState.kind === "error"
      ? treatmentsState.message
      : visitsState.kind === "error"
        ? visitsState.message
        : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Treatments</CardTitle>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!loading && errored && (
          <p className="text-sm text-destructive">Couldn’t load treatments: {errored}</p>
        )}
        {!loading && !errored && treatmentsState.kind === "ready" && (
          treatmentsState.data.total === 0 ? (
            <p className="text-sm text-muted-foreground">No treatments yet.</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {treatmentsState.data.items.map((t) => (
                <TreatmentCard
                  key={t.id}
                  treatment={t}
                  visits={visitsByTreatment.get(t.id) ?? []}
                  canManage={canManage}
                  onChanged={onChanged}
                />
              ))}
            </ul>
          )
        )}
      </CardContent>
    </Card>
  );
}

function TreatmentCard({
  treatment,
  visits,
  canManage,
  onChanged,
}: {
  treatment: Treatment;
  visits: Visit[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const open = treatment.status === "in_progress";
  // Open treatments start expanded (they're the actionable ones); completed
  // ones collapse to keep old cases out of the way.
  const [expanded, setExpanded] = useState(open);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError("This treatment’s status just changed. Refreshing…");
      onChanged();
      return;
    }
    setError(result.error);
  }

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="flex items-center gap-2 text-left"
          aria-expanded={expanded}
        >
          <span className="w-3 text-xs text-muted-foreground">
            {expanded ? "▾" : "▸"}
          </span>
          <span className="font-medium">{treatment.title}</span>
        </button>
        {treatment.tooth_ref && (
          <span className="text-sm text-muted-foreground">
            tooth {treatment.tooth_ref}
          </span>
        )}
        <TreatmentStatus status={treatment.status} />
        <span className="text-xs text-muted-foreground">
          {visits.length} {visits.length === 1 ? "visit" : "visits"}
        </span>
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
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {expanded && (
        <div className="ml-5 border-l pl-4">
          {visits.length === 0 ? (
            <p className="py-1 text-sm text-muted-foreground">
              No visits recorded yet.
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {visits.map((v) => (
                <VisitRow key={v.id} visit={v} />
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

// One sitting under its treatment. The treatment title/status live on the parent
// card now, so a visit row is just: when, what was noted, what was done.
function VisitRow({ visit }: { visit: Visit }) {
  const hasContent =
    (visit.clinical_notes && visit.clinical_notes.trim()) ||
    (visit.complaint && visit.complaint.trim()) ||
    visit.procedures.length > 0;

  return (
    <li className="flex flex-col gap-1 py-2 first:pt-0 last:pb-0">
      <span className="text-sm text-muted-foreground">
        {formatVisitDate(visit.visit_date)}
      </span>
      {visit.complaint && visit.complaint.trim() && (
        <p className="text-sm">
          <span className="text-muted-foreground">Complaint: </span>
          <span className="whitespace-pre-wrap">{visit.complaint}</span>
        </p>
      )}
      {visit.clinical_notes && visit.clinical_notes.trim() && (
        <p className="text-sm whitespace-pre-wrap">{visit.clinical_notes}</p>
      )}
      {visit.procedures.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {visit.procedures
            .map((p) => (p.tooth_ref ? `${p.treatment_item_name} (${p.tooth_ref})` : p.treatment_item_name))
            .join(" · ")}
        </p>
      )}
      {/* A bare visit still records that the patient was seen that day. */}
      {!hasContent && (
        <p className="text-sm text-muted-foreground">No notes recorded.</p>
      )}

      <VisitBilling visit={visit} />
    </li>
  );
}

// The per-visit billing control (5.4). Resolves whether the visit already has an
// invoice: if not, a "Generate invoice" link to the generate screen; if so, its
// status + a "View invoice" link. Billing is front-desk work, so there's no role
// gate here (unlike "Record visit") — the API is the guard.
function VisitBilling({ visit }: { visit: Visit }) {
  const inv = useVisitInvoice(visit.id);

  if (inv.kind === "loading") return null;
  if (inv.kind === "error") {
    return <p className="text-xs text-destructive">Billing: {inv.message}</p>;
  }

  if (inv.kind === "none") {
    return (
      <Link
        href={`/invoices/new/${visit.id}`}
        className={buttonVariants({ variant: "outline", size: "sm" }) + " mt-1 w-fit"}
      >
        Generate invoice
      </Link>
    );
  }

  return (
    <div className="mt-1 flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">Invoice: {statusLabel(inv.invoice.status)}</span>
      <Link href={`/invoices/${inv.invoice.id}`} className="underline">
        View invoice
      </Link>
    </div>
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
