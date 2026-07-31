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

import { useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { MedicalNotesBanner } from "@/components/medical-notes-banner";
import { ToothChart } from "@/components/tooth-chart";
import { useChart } from "@/lib/use-chart";
import {
  ClinicalRecordSection,
  EMPTY_CLINICAL,
  toClinicalBody,
  type ClinicalFields,
} from "./clinical-record-section";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { bookAppointment } from "@/lib/use-appointments";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { usePatient } from "@/lib/use-patient";
import { useStaff } from "@/lib/use-staff";
import {
  formatPrice,
  useTreatmentItems,
  type ItemKind,
} from "@/lib/use-treatment-items";
import { usePatientTreatments, type Treatment } from "@/lib/use-treatments";
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
  const params = useSearchParams();
  // When the visit is started from a calendar appointment ("Start visit"), the
  // appointment id rides in as ?appointment=<id> so the visit links back to it.
  const appointmentId = params.get("appointment");
  const patientState = usePatient(patientId);
  const staffState = useCurrentStaff();
  const treatmentsState = usePatientTreatments(patientId, { openOnly: true });
  // Active catalogue items, split by kind (6.7) so the two sections each show
  // only their own list.
  const treatmentItemsState = useTreatmentItems(false, "treatment");
  const medicineItemsState = useTreatmentItems(false, "medicine");
  const dentists = useStaff("dentist");
  // The dental chart (6.11) — marked chairside while treating.
  const chart = useChart(patientId);
  const { settings } = useClinicSettings();
  const slotMinutes = settings.slot_minutes;

  // The optional consulting (second) dentist for this sitting.
  const [consultingId, setConsultingId] = useState("");
  // Which submit button was pressed — a ref, not state, so the submit handler
  // reads the intent set in the same click event (state wouldn't have flushed).
  const draftInvoiceRef = useRef(false);
  // Same idea for "save, then send a sample to the lab" — the impression is taken
  // during the sitting, so the lab form is the natural next screen.
  const sendToLabRef = useRef(false);
  const dentistOptions = dentists.kind === "ready" ? dentists.items : [];

  // Which treatment this sitting belongs to: an existing id, or "new".
  const [choice, setChoice] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newTooth, setNewTooth] = useState("");

  const [complaint, setComplaint] = useState("");
  const [notes, setNotes] = useState("");
  // The OPD card's eighteen clinical fields, held as one object (6.10).
  const [clinical, setClinical] = useState<ClinicalFields>(EMPTY_CLINICAL);
  // Procedures and medicines are the SAME kind of row to the API (both are
  // `procedure_performed` pointing at a catalogue item) but are kept in separate
  // state so each section renders and edits only its own list. They're
  // concatenated at submit.
  const [procedures, setProcedures] = useState<ProcedureInput[]>([]);
  const [medicines, setMedicines] = useState<ProcedureInput[]>([]);
  // Consultation fees chosen for this sitting (6.7). These are NOT catalogue
  // items — the fee lives on the dentist — so they never become procedures.
  // They ride to the invoice screen as custom lines.
  const [consultFees, setConsultFees] = useState<
    { dentistId: string; name: string; amount: string }[]
  >([]);
  const [finished, setFinished] = useState(false);

  // Inline follow-up (4.6). Off by default; hidden when the treatment is being
  // completed (a finished treatment needs no next sitting).
  const [wantFollowUp, setWantFollowUp] = useState(false);
  const [fuDate, setFuDate] = useState("");
  const [fuTime, setFuTime] = useState("");
  // Blank = use the clinic's configured slot length (shown as the placeholder).
  const [fuDuration, setFuDuration] = useState("");
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

    const typed = Number(fuDuration);
    const result = await bookAppointment({
      patient_id: patientId,
      treatment_id: treatmentId,
      dentist_id: recorderId,
      start_time: start,
      // Blank or invalid → the clinic's configured slot length.
      duration_min: fuDuration.trim() && Number.isFinite(typed) && typed >= 5 ? typed : slotMinutes,
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
      appointment_id: appointmentId || null,
      consulting_dentist_id: consultingId || null,
      complaint: complaint.trim() || null,
      clinical_notes: notes.trim() || null,
      // The OPD card (6.10) — trimmed, blanks become nulls.
      ...toClinicalBody(clinical),
      // Both kinds go into the same list — the API stores them identically and
      // the item's own `kind` is what distinguishes them later.
      procedures: [...procedures, ...medicines].filter((p) => p.treatment_item_id),
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

    // "Draft invoice" closes the treat->bill loop: go to the generate-invoice
    // screen for the visit just recorded. Otherwise back to the profile.
    if (draftInvoiceRef.current) {
      // Any consultation fees chosen ride along as custom lines (6.7). They
      // have no catalogue row, so there's nothing on the visit to read them
      // back from — the query string is how they reach the invoice screen,
      // where they're pre-filled and still editable.
      //
      // These carry a DENTIST's name and an amount. No patient identifier, so
      // the "no patient identifiers in URLs" rule holds.
      const qs = new URLSearchParams();
      for (const fee of consultFees) {
        qs.append("consult", `${fee.amount}|${fee.name}`);
      }
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      router.push(`/invoices/new/${result.visit.id}${suffix}`);
      return;
    }
    // "Send to lab" carries the visit + appointment + patient into the lab form, so
    // the case is linked to the sitting the impression was taken at.
    if (sendToLabRef.current) {
      // Read the name off the state (the `patient` const is declared below this
      // function, so it isn't in scope here).
      const qs = new URLSearchParams({
        patient: patientId,
        name: patientState.kind === "ready" ? patientState.patient.name : "",
        visit: result.visit.id,
      });
      if (appointmentId) qs.set("appointment", appointmentId);
      router.push(`/lab/new?${qs.toString()}`);
      return;
    }
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
              <div className="flex flex-col gap-1">
                <label htmlFor="consulting" className="text-xs text-muted-foreground">
                  Consulting dentist (optional)
                </label>
                <select
                  id="consulting"
                  value={consultingId}
                  onChange={(e) => setConsultingId(e.target.value)}
                  className={`${controlClass} w-72`}
                >
                  <option value="">— none —</option>
                  {dentistOptions.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <span className="text-xs text-muted-foreground">
                  Set this if a second dentist took over the treatment this sitting.
                </span>
              </div>
            </CardContent>
          </Card>

          {/* --- the OPD card: history, vitals, examination, investigations,
                 diagnosis, referral (6.10). Ordered as the paper card is, so it
                 can be transcribed top-to-bottom. --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Examination &amp; diagnosis</CardTitle>
            </CardHeader>
            <CardContent>
              <ClinicalRecordSection value={clinical} onChange={setClinical} />
            </CardContent>
          </Card>

          {/* --- the dental chart (6.11) --- marked while treating, which is
                 what keeps it current instead of rotting. Saves immediately
                 (it's the patient's chart, not this form's draft), so it
                 stands on its own even if the visit isn't saved. --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Dental chart</CardTitle>
            </CardHeader>
            <CardContent>
              {chart.kind === "ready" ? (
                <ToothChart
                  patientId={patientId}
                  items={chart.items}
                  onChanged={chart.refetch}
                  editable
                  patientAge={patient.age}
                />
              ) : (
                <p className="text-sm text-muted-foreground">Loading chart…</p>
              )}
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
                itemsState={treatmentItemsState}
                kind="treatment"
              />
            </CardContent>
          </Card>

          {/* --- medicine (6.7) --- same rows, no tooth field --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Medicine given</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <ProcedureRows
                procedures={medicines}
                setProcedures={setMedicines}
                itemsState={medicineItemsState}
                kind="medicine"
              />
            </CardContent>
          </Card>

          {/* --- consultation fee (6.7) --- offered, never auto-charged --- */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Consultation fee</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <ConsultationFeeRows
                dentists={dentistOptions}
                primaryId={staffState.kind === "staff" ? staffState.staff.id : null}
                consultingId={consultingId}
                chosen={consultFees}
                setChosen={setConsultFees}
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
                        placeholder={String(slotMinutes)}
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

          <div className="flex flex-wrap items-center gap-3">
            {/* Disabled while in flight: a double-submit would record the
                sitting twice. After the visit has saved (savedTreatmentId set),
                the button only retries the follow-up booking. */}
            <Button
              type="submit"
              disabled={busy || effectiveChoice === null}
              onClick={() => {
                draftInvoiceRef.current = false;
                sendToLabRef.current = false;
              }}
            >
              {busy
                ? savedTreatmentId
                  ? "Booking…"
                  : "Recording…"
                : savedTreatmentId
                  ? "Book follow-up"
                  : "Record visit"}
            </Button>

            {/* Save and go straight to billing — the chairside → bill hand-off.
                Hidden once we're only retrying a follow-up booking. */}
            {!savedTreatmentId && (
              <Button
                type="submit"
                variant="secondary"
                disabled={busy || effectiveChoice === null}
                onClick={() => {
                  draftInvoiceRef.current = true;
                  sendToLabRef.current = false;
                }}
              >
                Save &amp; draft invoice
              </Button>
            )}

            {/* Save and go straight to the lab form — for the sitting where an
                impression was taken. The case comes back linked to this visit. */}
            {!savedTreatmentId && (
              <Button
                type="submit"
                variant="outline"
                disabled={busy || effectiveChoice === null}
                onClick={() => {
                  draftInvoiceRef.current = false;
                  sendToLabRef.current = true;
                }}
              >
                Save &amp; send to lab
              </Button>
            )}

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

// Per-kind wording + behaviour for the shared rows component. A tooth number is
// meaningful on a procedure and noise on an antibiotic, so `tooth` gates it.
const ROW_LABELS: Record<
  ItemKind,
  { picker: string; add: string; empty: string; none: string; tooth: boolean }
> = {
  treatment: {
    picker: "Procedure",
    add: "Add procedure",
    empty: "No treatments in the catalogue yet.",
    none: "None added. A visit can be recorded without procedures, but billing works from them.",
    tooth: true,
  },
  medicine: {
    picker: "Medicine",
    add: "Add medicine",
    empty: "No medicines in the catalogue yet.",
    none: "None given.",
    tooth: false,
  },
};

function ProcedureRows({
  procedures,
  setProcedures,
  itemsState,
  kind,
}: {
  procedures: ProcedureInput[];
  setProcedures: (p: ProcedureInput[]) => void;
  itemsState: ItemsState;
  kind: ItemKind;
}) {
  const labels = ROW_LABELS[kind];

  if (itemsState.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (itemsState.kind === "error") {
    return (
      <p className="text-sm text-destructive">
        Couldn’t load the catalogue: {itemsState.message}
      </p>
    );
  }

  const items = itemsState.data.items;

  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {labels.empty} An admin can add them under Settings → Pricing.
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
        <p className="text-sm text-muted-foreground">{labels.none}</p>
      )}

      {procedures.map((proc, index) => {
        const item = items.find((i) => i.id === proc.treatment_item_id);
        return (
          <div key={index} className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <label
                htmlFor={`${kind}-${index}`}
                className="text-xs text-muted-foreground"
              >
                {labels.picker}
              </label>
              <select
                id={`${kind}-${index}`}
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
            {labels.tooth && (
              <div className="flex flex-col gap-1">
                <label
                  htmlFor={`tooth-${kind}-${index}`}
                  className="text-xs text-muted-foreground"
                >
                  Tooth (optional)
                </label>
                <Input
                  id={`tooth-${kind}-${index}`}
                  value={proc.tooth_ref ?? ""}
                  onChange={(e) => update(index, { tooth_ref: e.target.value })}
                  placeholder="36"
                  className="w-24"
                />
              </div>
            )}
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
          {labels.add}
        </Button>
      </div>
    </>
  );
}

// The consultation-fee section (6.7).
//
// The fee is per-dentist, so this offers the fee belonging to THIS sitting's
// dentists — the recording dentist and, if set, the consulting one. It is
// **offered, never automatic**: a follow-up sitting must not silently re-bill a
// consultation, so nothing is charged until someone clicks Add.
//
// A dentist with no fee set is listed but not addable — a ₹0 consultation the
// receptionist never intended is worse than an obvious gap.
function ConsultationFeeRows({
  dentists,
  primaryId,
  consultingId,
  chosen,
  setChosen,
}: {
  dentists: { id: string; name: string; consultation_fee: string | null }[];
  primaryId: string | null;
  consultingId: string;
  chosen: { dentistId: string; name: string; amount: string }[];
  setChosen: (
    f: { dentistId: string; name: string; amount: string }[],
  ) => void;
}) {
  // The dentists relevant to this sitting, de-duplicated (the consulting
  // dentist may be the same person as the recorder).
  const relevant = [primaryId, consultingId || null]
    .filter((id): id is string => Boolean(id))
    .filter((id, i, all) => all.indexOf(id) === i)
    .map((id) => dentists.find((d) => d.id === id))
    .filter((d): d is (typeof dentists)[number] => Boolean(d));

  if (relevant.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No dentist on this visit yet — pick one above to see their consultation
        fee.
      </p>
    );
  }

  return (
    <>
      {relevant.map((d) => {
        const already = chosen.some((c) => c.dentistId === d.id);
        const role = d.id === primaryId ? "primary" : "consulting";

        return (
          <div key={d.id} className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium">{d.name}</span>
            <span className="text-xs text-muted-foreground">({role})</span>

            {d.consultation_fee === null ? (
              <span className="text-xs text-muted-foreground">
                No fee set — add one under Settings → Pricing.
              </span>
            ) : (
              <>
                <span className="tabular-nums text-muted-foreground">
                  {formatPrice(d.consultation_fee)}
                </span>
                {already ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setChosen(chosen.filter((c) => c.dentistId !== d.id))
                    }
                  >
                    Remove
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setChosen([
                        ...chosen,
                        {
                          dentistId: d.id,
                          name: d.name,
                          amount: d.consultation_fee as string,
                        },
                      ])
                    }
                  >
                    Add to bill
                  </Button>
                )}
              </>
            )}
          </div>
        );
      })}

      <p className="text-xs text-muted-foreground">
        Added fees appear on the invoice when you choose “Save &amp; draft
        invoice”. Nothing is charged unless you add it.
      </p>
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
