"use client";

// The OPD record sheet (6.10) — one visit, laid out like the clinic's paper
// out-patient card so a printed copy is recognisable to anyone used to the
// original: header, patient block, complaint, history, examination,
// investigations, diagnosis, treatment done, signature line.
//
// Rows whose value is empty are omitted rather than printed blank: a sheet full
// of empty labels is harder to read than a short one, and the paper card's
// unused lines were simply left unwritten too.

import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { usePatient } from "@/lib/use-patient";
import {
  INVESTIGATION_LABELS,
  formatVisitDate,
  formatVisitNumber,
  useVisit,
  type Visit,
} from "@/lib/use-visits";
import { phaseLabel } from "@/lib/use-treatments";

export function OpdSheet({ visitId }: { visitId: string }) {
  const state = useVisit(visitId);

  if (state.kind === "loading") {
    return <main className="mx-auto max-w-2xl p-8 text-sm text-muted-foreground">Loading…</main>;
  }
  if (state.kind === "not-found") {
    return <main className="mx-auto max-w-2xl p-8 text-sm text-muted-foreground">Visit not found.</main>;
  }
  if (state.kind === "error") {
    return <main className="mx-auto max-w-2xl p-8 text-sm text-destructive">{state.message}</main>;
  }

  return <Loaded visit={state.visit} />;
}

/** One label/value line. Renders nothing when there's no value. */
function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex gap-3 border-b border-dotted py-1 text-sm last:border-0">
      <span className="w-52 shrink-0 text-muted-foreground">{label}</span>
      <span className="flex-1">{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  // Hide the whole block when every Row inside decided not to render.
  const hasContent = Array.isArray(children)
    ? children.some(Boolean)
    : Boolean(children);
  if (!hasContent) return null;
  return (
    <section className="flex flex-col gap-1">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      <div>{children}</div>
    </section>
  );
}

function Loaded({ visit }: { visit: Visit }) {
  const { settings } = useClinicSettings();
  const patientState = usePatient(visit.patient_id);
  const p = patientState.kind === "ready" ? patientState.patient : null;

  const bp =
    visit.bp_systolic && visit.bp_diastolic
      ? `${visit.bp_systolic}/${visit.bp_diastolic} mmHg`
      : null;

  const investigations = visit.investigations.length
    ? visit.investigations.map((i) => INVESTIGATION_LABELS[i]).join(", ") +
      (visit.investigation_notes ? ` — ${visit.investigation_notes}` : "")
    : null;

  const referral = visit.referred_to
    ? visit.referred_to + (visit.referral_note ? ` — ${visit.referral_note}` : "")
    : null;

  // Any examination finding at all? Used to drop the whole block when the visit
  // was a simple one (a scaling fills none of it).
  const exam = [
    ["Habits", visit.habits],
    ["Extra oral", visit.extra_oral],
    ["Intra oral", visit.intra_oral],
    ["Soft tissues", visit.soft_tissues],
    ["Hard tissue / caries", visit.hard_tissue],
    ["Occlusion", visit.occlusion],
    ["Missing teeth", visit.missing_teeth],
    ["Others", visit.other_findings],
  ] as const;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between no-print">
        <Link
          href={`/patients/${visit.patient_id}`}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Back to patient
        </Link>
        <Button size="sm" onClick={() => window.print()}>
          Print
        </Button>
      </div>

      {/* --- clinic header --- */}
      <header className="border-b pb-3 text-center">
        <h1 className="text-lg font-semibold">{settings.clinic_name}</h1>
        {settings.address && (
          <p className="text-xs text-muted-foreground">{settings.address}</p>
        )}
        {settings.phone && (
          <p className="text-xs text-muted-foreground">Ph: {settings.phone}</p>
        )}
        <p className="mt-2 text-sm font-medium">Out-patient Record</p>
      </header>

      {/* --- patient block --- */}
      <section className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <div>
          <span className="text-muted-foreground">OP No: </span>
          <span className="font-medium">{formatVisitNumber(visit.number)}</span>
        </div>
        <div className="text-right">
          <span className="text-muted-foreground">Date: </span>
          {formatVisitDate(visit.visit_date)}
        </div>
        <div className="col-span-2 border-t pt-1">
          <span className="text-muted-foreground">Name: </span>
          <span className="font-medium">{p?.name ?? "—"}</span>
        </div>
        {p?.guardian_name && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Parent/Guardian: </span>
            {p.guardian_name}
          </div>
        )}
        <div>
          <span className="text-muted-foreground">Age: </span>
          {p?.age ?? "—"}
        </div>
        <div>
          <span className="text-muted-foreground">Sex: </span>
          {p?.gender ?? "—"}
        </div>
        <div>
          <span className="text-muted-foreground">Phone: </span>
          {p?.phone ?? "—"}
        </div>
        {p?.address && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Address: </span>
            {p.address}
          </div>
        )}
      </section>

      <Section title="Complaint & history">
        <Row label="Chief complaint" value={visit.complaint} />
        <Row label="Medical / drug / allergy" value={visit.history_note} />
        <Row label="Blood pressure" value={bp} />
      </Section>

      <Section title="Examination">
        {exam.map(([label, v]) => (
          <Row key={label} label={label} value={v} />
        ))}
      </Section>

      <Section title="Investigations">
        <Row label="Ordered" value={investigations} />
      </Section>

      <Section title="Diagnosis">
        <Row label="Provisional diagnosis" value={visit.provisional_diagnosis} />
        <Row label="Differential (D/D)" value={visit.differential_diagnosis} />
        <Row label="Final diagnosis" value={visit.final_diagnosis} />
      </Section>

      <Section title="Treatment">
        <Row
          label="Case"
          value={
            visit.treatment.title +
            (visit.treatment.tooth_ref ? ` — tooth ${visit.treatment.tooth_ref}` : "")
          }
        />
        <Row label="Phase" value={phaseLabel(visit.treatment.phase)} />
        <Row
          label="Done this sitting"
          value={
            visit.procedures.length
              ? visit.procedures
                  .map(
                    (pr) =>
                      pr.treatment_item_name +
                      (pr.tooth_ref ? ` (${pr.tooth_ref})` : ""),
                  )
                  .join(", ")
              : null
          }
        />
        <Row label="Notes" value={visit.clinical_notes} />
        <Row label="Referred to" value={referral} />
      </Section>

      {/* --- signature, as on the paper card --- */}
      <footer className="mt-6 flex justify-end border-t pt-6 text-sm">
        <div className="text-center">
          <div className="h-10" />
          <div className="border-t px-8 pt-1">
            {visit.dentist_name ?? "Dentist"}
            {visit.consulting_dentist_name && (
              <span className="block text-xs text-muted-foreground">
                Consulting: {visit.consulting_dentist_name}
              </span>
            )}
          </div>
        </div>
      </footer>
    </main>
  );
}
