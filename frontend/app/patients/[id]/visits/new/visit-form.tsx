"use client";

// The visit record screen (step 4.4) — what Phase 4 is for.
//
// It submits the 4.3 POST /visits contract, whose central rule is EITHER
// continue an existing treatment OR start a new one. That's modelled here as a
// radio group whose value is either a treatment id or the literal "new", so the
// invalid "both / neither" request is unrepresentable in the UI (the API
// validates it too — this is convenience, not the guard).
//
// The "this treatment is now complete" checkbox drives `treatment_status`, which
// is what auto-closes single-visit work. Leaving it unchecked keeps the thread
// open so it shows up for follow-up (4.8).
//
// Role gate: recording is dentist/admin on the API. Non-dentists get a note
// instead of the form — again convenience; a 403 is still surfaced inline.
//
// Plain styling on purpose: visual polish is Phase 6.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { MedicalNotesBanner } from "@/components/medical-notes-banner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { usePatient } from "@/lib/use-patient";
import { formatPrice, useTreatmentItems } from "@/lib/use-treatment-items";
import { usePatientTreatments, type Treatment } from "@/lib/use-treatments";
import {
  recordVisit,
  type ProcedureInput,
  type VisitCreateBody,
} from "@/lib/use-visits";
import type { MutationResult } from "@/lib/use-treatment-items";

const NEW_TREATMENT = "new";

// Shared styling for the native controls we don't have shadcn components for.
// Matches components/ui/input.tsx closely enough to look of a piece.
const controlClass =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50";

function messageFor(result: MutationResult): string | null {
  if (result === "ok") return null;
  if (result === "forbidden")
    return "Only a dentist can record visits. Ask a dentist to record this one.";
  if (result === "conflict")
    return "That treatment is already completed, so a new sitting can't be added to it. Start a new treatment instead.";
  return result.error;
}

export function VisitForm({ patientId }: { patientId: string }) {
  const router = useRouter();
  const patientState = usePatient(patientId);
  const staffState = useCurrentStaff();
  const treatmentsState = usePatientTreatments(patientId, { openOnly: true });
  const itemsState = useTreatmentItems(false); // active catalogue items only

  // Which treatment this sitting belongs to: an existing id, or "new".
  const [choice, setChoice] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newTooth, setNewTooth] = useState("");

  const [complaint, setComplaint] = useState("");
  const [notes, setNotes] = useState("");
  const [procedures, setProcedures] = useState<ProcedureInput[]>([]);
  const [finished, setFinished] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openTreatments: Treatment[] =
    treatmentsState.kind === "ready" ? treatmentsState.data.items : [];

  // Default the radio once treatments have loaded: continue the only open
  // thread if there's exactly one, otherwise start new. Derived rather than
  // stored so it can't fight the user's explicit choice.
  const effectiveChoice =
    choice ??
    (treatmentsState.kind === "ready"
      ? openTreatments.length === 1
        ? openTreatments[0].id
        : NEW_TREATMENT
      : null);

  const isNew = effectiveChoice === NEW_TREATMENT;

  const canRecord = useMemo(() => {
    if (staffState.kind !== "staff") return false;
    return (
      staffState.staff.roles.includes("dentist") ||
      staffState.staff.roles.includes("admin")
    );
  }, [staffState]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (effectiveChoice === null) return;
    if (isNew && !newTitle.trim()) {
      setError("Give the new treatment a title, e.g. “RCT tooth 36”.");
      return;
    }

    // Exactly one of treatment_id / treatment — the union type enforces it.
    const choicePart: Pick<VisitCreateBody, "treatment_id" | "treatment"> = isNew
      ? {
          treatment: {
            title: newTitle.trim(),
            tooth_ref: newTooth.trim() || null,
          },
        }
      : { treatment_id: effectiveChoice };

    const body = {
      patient_id: patientId,
      ...choicePart,
      complaint: complaint.trim() || null,
      clinical_notes: notes.trim() || null,
      procedures: procedures.filter((p) => p.treatment_item_id),
      treatment_status: finished ? "completed" : "in_progress",
    } as VisitCreateBody;

    setBusy(true);
    const result = await recordVisit(body);
    setBusy(false);

    const msg = messageFor(result);
    if (msg) {
      setError(msg);
      return;
    }
    // Back to the profile, where the new visit shows in the history.
    router.push(`/patients/${patientId}`);
    router.refresh();
  }

  if (patientState.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (patientState.kind === "not-found") {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">Patient not found.</p>
        <BackLink patientId={patientId} />
      </div>
    );
  }
  if (patientState.kind === "error") {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-destructive">
          Couldn’t load the patient: {patientState.message}
        </p>
        <BackLink patientId={patientId} />
      </div>
    );
  }

  const patient = patientState.patient;

  return (
    <div className="flex flex-col gap-6">
      <BackLink patientId={patientId} />

      <div>
        <h1 className="text-xl font-semibold">Record visit</h1>
        <p className="text-sm text-muted-foreground">{patient.name}</p>
      </div>

      {/* The reason this screen keeps patient context: allergies and blood
          thinners matter most at the moment of treatment. */}
      <MedicalNotesBanner notes={patient.medical_notes} />

      {!canRecord && staffState.kind === "staff" && (
        <p className="rounded-md border border-muted bg-muted/40 p-3 text-sm text-muted-foreground">
          Only a dentist can record visits. You can view this patient’s history
          on their profile.
        </p>
      )}

      {canRecord && (
        <form onSubmit={submit} className="flex flex-col gap-6">
          {/* --- which treatment --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Treatment</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {treatmentsState.kind === "loading" && (
                <p className="text-sm text-muted-foreground">
                  Loading treatments…
                </p>
              )}
              {treatmentsState.kind === "error" && (
                <p className="text-sm text-destructive">
                  Couldn’t load open treatments: {treatmentsState.message}
                </p>
              )}

              {openTreatments.map((t) => (
                <label
                  key={t.id}
                  className="flex cursor-pointer items-start gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="treatment"
                    className="mt-1"
                    checked={effectiveChoice === t.id}
                    onChange={() => setChoice(t.id)}
                  />
                  <span>
                    <span className="font-medium">{t.title}</span>
                    {t.tooth_ref && (
                      <span className="text-muted-foreground">
                        {" "}
                        · tooth {t.tooth_ref}
                      </span>
                    )}
                    <span className="block text-xs text-muted-foreground">
                      in progress — continue this treatment
                    </span>
                  </span>
                </label>
              ))}

              <label className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="treatment"
                  className="mt-1"
                  checked={isNew}
                  onChange={() => setChoice(NEW_TREATMENT)}
                />
                <span>
                  <span className="font-medium">Start new treatment</span>
                  {openTreatments.length === 0 &&
                    treatmentsState.kind === "ready" && (
                      <span className="block text-xs text-muted-foreground">
                        This patient has no treatments in progress.
                      </span>
                    )}
                </span>
              </label>

              {isNew && (
                <div className="ml-6 flex flex-wrap items-end gap-3">
                  <div className="flex flex-col gap-1">
                    <label
                      htmlFor="new-title"
                      className="text-xs text-muted-foreground"
                    >
                      What is being done
                    </label>
                    <Input
                      id="new-title"
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                      placeholder="e.g. RCT tooth 36"
                      className="w-64"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label
                      htmlFor="new-tooth"
                      className="text-xs text-muted-foreground"
                    >
                      Tooth (optional)
                    </label>
                    <Input
                      id="new-tooth"
                      value={newTooth}
                      onChange={(e) => setNewTooth(e.target.value)}
                      placeholder="36"
                      className="w-24"
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* --- what happened --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">This sitting</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <label htmlFor="complaint" className="text-xs text-muted-foreground">
                  Complaint
                </label>
                <textarea
                  id="complaint"
                  value={complaint}
                  onChange={(e) => setComplaint(e.target.value)}
                  rows={2}
                  placeholder="What the patient came in with"
                  className={controlClass}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="notes" className="text-xs text-muted-foreground">
                  Clinical notes
                </label>
                <textarea
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={4}
                  placeholder="What you observed and did"
                  className={controlClass}
                />
              </div>
            </CardContent>
          </Card>

          {/* --- procedures --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Procedures done</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <ProcedureRows
                procedures={procedures}
                setProcedures={setProcedures}
                itemsState={itemsState}
              />
            </CardContent>
          </Card>

          {/* --- finished? --- */}
          <Card>
            <CardContent className="pt-6">
              <label className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={finished}
                  onChange={(e) => setFinished(e.target.checked)}
                />
                <span>
                  <span className="font-medium">This treatment is now complete</span>
                  <span className="block text-xs text-muted-foreground">
                    Leave unchecked if the patient needs another sitting — the
                    treatment stays open so it can be followed up.
                  </span>
                </span>
              </label>
            </CardContent>
          </Card>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex items-center gap-3">
            {/* Disabled while in flight: a double-submit would record the
                sitting twice. */}
            <Button type="submit" disabled={busy || effectiveChoice === null}>
              {busy ? "Recording…" : "Record visit"}
            </Button>
            <Link
              href={`/patients/${patientId}`}
              className="text-sm text-muted-foreground hover:underline"
            >
              Cancel
            </Link>
          </div>
        </form>
      )}
    </div>
  );
}

type ItemsState = ReturnType<typeof useTreatmentItems>;

function ProcedureRows({
  procedures,
  setProcedures,
  itemsState,
}: {
  procedures: ProcedureInput[];
  setProcedures: (p: ProcedureInput[]) => void;
  itemsState: ItemsState;
}) {
  if (itemsState.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading catalogue…</p>;
  }
  if (itemsState.kind === "error") {
    return (
      <p className="text-sm text-destructive">
        Couldn’t load the treatment catalogue: {itemsState.message}
      </p>
    );
  }

  const items = itemsState.data.items;

  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No treatments in the catalogue yet. An admin can add them under Settings
        → Treatments.
      </p>
    );
  }

  function update(index: number, changes: Partial<ProcedureInput>) {
    setProcedures(
      procedures.map((p, i) => (i === index ? { ...p, ...changes } : p)),
    );
  }

  return (
    <>
      {procedures.length === 0 && (
        <p className="text-sm text-muted-foreground">
          None added. A visit can be recorded without procedures, but billing
          (later) works from them.
        </p>
      )}

      {procedures.map((proc, index) => {
        const item = items.find((i) => i.id === proc.treatment_item_id);
        return (
          <div key={index} className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <label
                htmlFor={`proc-${index}`}
                className="text-xs text-muted-foreground"
              >
                Procedure
              </label>
              <select
                id={`proc-${index}`}
                value={proc.treatment_item_id}
                onChange={(e) =>
                  update(index, { treatment_item_id: e.target.value })
                }
                className={`${controlClass} w-64`}
              >
                {items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label
                htmlFor={`tooth-${index}`}
                className="text-xs text-muted-foreground"
              >
                Tooth (optional)
              </label>
              <Input
                id={`tooth-${index}`}
                value={proc.tooth_ref ?? ""}
                onChange={(e) => update(index, { tooth_ref: e.target.value })}
                placeholder="36"
                className="w-24"
              />
            </div>
            {/* Price is context only — never used in arithmetic here (money
                stays a decimal string; totals are Phase 5's job). */}
            {item && (
              <span className="pb-2 text-sm text-muted-foreground">
                {formatPrice(item.default_price)}
              </span>
            )}
            <Button
              type="button"
              variant="ghost"
              className="mb-0.5"
              onClick={() =>
                setProcedures(procedures.filter((_, i) => i !== index))
              }
            >
              Remove
            </Button>
          </div>
        );
      })}

      <div>
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            setProcedures([
              ...procedures,
              { treatment_item_id: items[0].id, tooth_ref: "" },
            ])
          }
        >
          Add procedure
        </Button>
      </div>
    </>
  );
}

function BackLink({ patientId }: { patientId: string }) {
  return (
    <Link
      href={`/patients/${patientId}`}
      className="text-sm text-muted-foreground hover:underline"
    >
      ← Back to patient
    </Link>
  );
}
