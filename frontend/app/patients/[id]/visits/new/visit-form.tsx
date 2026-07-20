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
import { bookAppointment } from "@/lib/use-appointments";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { usePatient } from "@/lib/use-patient";
import { formatPrice, useTreatmentItems } from "@/lib/use-treatment-items";
import { usePatientTreatments, type Treatment } from "@/lib/use-treatments";
import { SLOT_MIN } from "@/lib/week";
import {
  recordVisit,
  type ProcedureInput,
  type RecordVisitResult,
  type VisitCreateBody,
} from "@/lib/use-visits";

const NEW_TREATMENT = "new";

// Shared styling for the native controls we don't have shadcn components for.
// Matches components/ui/input.tsx closely enough to look of a piece.
const controlClass =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50";

// A visit-record failure -> a user-facing message. `ok` never reaches here.
function recordVisitMessage(result: RecordVisitResult): string {
  if (result.status === "forbidden")
    return "Only a dentist can record visits. Ask a dentist to record this one.";
  if (result.status === "conflict")
    return "That treatment is already completed, so a new sitting can't be added to it. Start a new treatment instead.";
  if (result.status === "error") return result.message;
  return "Could not record the visit.";
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

  // Inline follow-up (4.6). Off by default; hidden when the treatment is being
  // completed (a finished treatment needs no next sitting).
  const [wantFollowUp, setWantFollowUp] = useState(false);
  const [fuDate, setFuDate] = useState("");
  const [fuTime, setFuTime] = useState("");
  const [fuDuration, setFuDuration] = useState(String(SLOT_MIN));
  const [fuReason, setFuReason] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Once the visit is recorded, a failed follow-up must NOT re-record it. This
  // holds the created treatment id so a retry only books the appointment.
  const [savedTreatmentId, setSavedTreatmentId] = useState<string | null>(null);

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

  // The recorder's id, used as the follow-up's dentist by default.
  const recorderId =
    staffState.kind === "staff" ? staffState.staff.id : null;

  // Build the ISO start_time from the native date + time inputs, in the
  // browser's local zone (same convention as the calendar — the clinic-timezone
  // fix is still Phase 4). Returns null if either field is blank.
  function followUpStart(): string | null {
    if (!fuDate || !fuTime) return null;
    const dt = new Date(`${fuDate}T${fuTime}`);
    return Number.isNaN(dt.getTime()) ? null : dt.toISOString();
  }

  // Books the follow-up against an already-created treatment. Returns true on
  // success (or when no follow-up was requested); false leaves the form up with
  // a notice so the booking can be retried without re-recording the visit.
  async function bookFollowUpFor(treatmentId: string): Promise<boolean> {
    if (!(wantFollowUp && !finished)) return true;

    const start = followUpStart();
    if (!start) {
      setNotice(
        "Visit recorded. Pick a date and time for the follow-up, or leave it and book from the calendar later.",
      );
      return false;
    }

    const duration = Number(fuDuration);
    const result = await bookAppointment({
      patient_id: patientId,
      treatment_id: treatmentId,
      dentist_id: recorderId,
      start_time: start,
      duration_min: Number.isFinite(duration) && duration >= 5 ? duration : SLOT_MIN,
      reason: fuReason.trim() || null,
    });

    if (result === "ok") return true;
    if (result === "conflict") {
      setNotice(
        "Visit recorded. The follow-up wasn’t booked — that slot is already taken. Pick another time and try again, or book it from the calendar.",
      );
    } else if (result === "forbidden") {
      setNotice("Visit recorded, but you’re not allowed to book appointments.");
    } else {
      setNotice(`Visit recorded, but the follow-up wasn’t booked: ${result.error}`);
    }
    return false;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);

    setBusy(true);

    // Retry path: the visit already saved on a previous submit and only the
    // follow-up failed — book against the saved treatment, don't re-record.
    if (savedTreatmentId) {
      const booked = await bookFollowUpFor(savedTreatmentId);
      setBusy(false);
      if (booked) {
        router.push(`/patients/${patientId}`);
        router.refresh();
      }
      return;
    }

    if (effectiveChoice === null) {
      setBusy(false);
      return;
    }
    if (isNew && !newTitle.trim()) {
      setBusy(false);
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

    // Write 1: the visit. This is the durable one — if the follow-up fails
    // afterwards, the visit stays saved and we never re-record it.
    const result = await recordVisit(body);
    if (result.status !== "ok") {
      setBusy(false);
      setError(recordVisitMessage(result));
      return;
    }

    // Write 2: the optional follow-up, linked to the visit's treatment.
    const treatmentId = result.visit.treatment_id;
    const booked = await bookFollowUpFor(treatmentId);
    setBusy(false);

    if (!booked) {
      // Visit saved; follow-up outstanding. Remember the treatment so the next
      // submit only retries the booking.
      setSavedTreatmentId(treatmentId);
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
                  onChange={(e) => {
                    setFinished(e.target.checked);
                    // A completed treatment needs no follow-up.
                    if (e.target.checked) setWantFollowUp(false);
                  }}
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

          {/* --- inline follow-up (4.6) --- only when the treatment stays open */}
          {!finished && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Follow-up</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <label className="flex cursor-pointer items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={wantFollowUp}
                    onChange={(e) => setWantFollowUp(e.target.checked)}
                  />
                  <span>
                    <span className="font-medium">Book a follow-up appointment</span>
                    <span className="block text-xs text-muted-foreground">
                      Book the next sitting now. If you skip it, this treatment
                      will show up as needing a follow-up.
                    </span>
                  </span>
                </label>

                {wantFollowUp && (
                  <div className="ml-6 flex flex-wrap items-end gap-3">
                    <div className="flex flex-col gap-1">
                      <label htmlFor="fu-date" className="text-xs text-muted-foreground">
                        Date
                      </label>
                      <input
                        id="fu-date"
                        type="date"
                        value={fuDate}
                        onChange={(e) => setFuDate(e.target.value)}
                        className={`${controlClass} w-44`}
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label htmlFor="fu-time" className="text-xs text-muted-foreground">
                        Time
                      </label>
                      <input
                        id="fu-time"
                        type="time"
                        value={fuTime}
                        onChange={(e) => setFuTime(e.target.value)}
                        className={`${controlClass} w-32`}
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label htmlFor="fu-duration" className="text-xs text-muted-foreground">
                        Minutes
                      </label>
                      <Input
                        id="fu-duration"
                        value={fuDuration}
                        onChange={(e) => setFuDuration(e.target.value)}
                        inputMode="numeric"
                        className="w-20"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label htmlFor="fu-reason" className="text-xs text-muted-foreground">
                        Reason (optional)
                      </label>
                      <Input
                        id="fu-reason"
                        value={fuReason}
                        onChange={(e) => setFuReason(e.target.value)}
                        placeholder="e.g. RCT tooth 36 — next sitting"
                        className="w-72"
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
          {notice && (
            <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
              {notice}
            </p>
          )}

          <div className="flex items-center gap-3">
            {/* Disabled while in flight: a double-submit would record the
                sitting twice. After the visit has saved (savedTreatmentId set),
                the button only retries the follow-up booking. */}
            <Button type="submit" disabled={busy || effectiveChoice === null}>
              {busy
                ? savedTreatmentId
                  ? "Booking…"
                  : "Recording…"
                : savedTreatmentId
                  ? "Book follow-up"
                  : "Record visit"}
            </Button>
            <Link
              href={`/patients/${patientId}`}
              className="text-sm text-muted-foreground hover:underline"
            >
              {savedTreatmentId ? "Done — back to patient" : "Cancel"}
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
