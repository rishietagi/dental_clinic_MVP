"use client";

// Book-an-appointment form (6.3). Pick a patient (search, or pre-seeded via
// ?patient=<id>&name=<name>), a date/time/duration, a PRIMARY dentist and an
// optional CONSULTING dentist (the handoff), and a reason. Posts to
// POST /appointments; the DB's overlap constraint surfaces as an inline 409.
//
// Times are entered in local wall-clock via <input type="datetime-local"> and
// sent as an ISO string (the app's existing timezone treatment; the clinic-tz
// nuance is unchanged from the calendar).

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { bookAppointment } from "@/lib/use-appointments";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { usePatientSearch, type PatientListItem } from "@/lib/use-patient-search";
import { useStaff } from "@/lib/use-staff";

const controlClass =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

export function NewAppointmentForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { settings } = useClinicSettings();
  const dentists = useStaff("dentist");

  // A patient may be pre-selected (from a profile's "Book appointment").
  const seededId = params.get("patient");
  const seededName = params.get("name");
  const [patient, setPatient] = useState<{ id: string; name: string } | null>(
    seededId ? { id: seededId, name: seededName ?? "Selected patient" } : null,
  );

  const [query, setQuery] = useState("");
  const search = usePatientSearch(query);

  const [startLocal, setStartLocal] = useState("");
  const [duration, setDuration] = useState(String(settings.slot_minutes));
  const [dentistId, setDentistId] = useState("");
  const [consultingId, setConsultingId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dentistOptions = dentists.kind === "ready" ? dentists.items : [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!patient) {
      setError("Choose a patient.");
      return;
    }
    if (!startLocal) {
      setError("Choose a date and time.");
      return;
    }
    if (consultingId && consultingId === dentistId) {
      setError("The consulting dentist should be different from the primary dentist.");
      return;
    }

    setBusy(true);
    const result = await bookAppointment({
      patient_id: patient.id,
      start_time: new Date(startLocal).toISOString(),
      duration_min: Number(duration) || settings.slot_minutes,
      dentist_id: dentistId || null,
      consulting_dentist_id: consultingId || null,
      reason: reason.trim() || null,
    });
    setBusy(false);

    if (result === "ok") {
      toast.success("Appointment booked");
      router.push("/calendar");
      return;
    }
    if (result === "conflict") {
      setError("That slot overlaps an existing appointment for the primary dentist.");
      return;
    }
    if (result === "forbidden") {
      setError("You don’t have permission to book.");
      return;
    }
    setError(result.error);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      {/* Patient */}
      {patient ? (
        <div className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <span>
            <span className="text-muted-foreground">Patient: </span>
            <span className="font-medium">{patient.name}</span>
          </span>
          <button
            type="button"
            className="text-xs underline"
            onClick={() => {
              setPatient(null);
              setQuery("");
            }}
          >
            Change
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Patient *</label>
          <Input
            type="search"
            placeholder="Search by name or phone…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          {query.trim() !== "" && search.kind === "ready" && (
            <div className="mt-1 max-h-48 overflow-y-auto rounded-md border">
              {search.data.items.length === 0 ? (
                <p className="px-3 py-2 text-sm text-muted-foreground">No matches.</p>
              ) : (
                search.data.items.map((p: PatientListItem) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setPatient({ id: p.id, name: p.name })}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
                  >
                    <span>{p.name}</span>
                    <span className="text-muted-foreground">{p.phone ?? ""}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* When */}
      <div className="grid grid-cols-2 gap-4">
        <Field label="Date & time" required>
          <Input
            type="datetime-local"
            value={startLocal}
            onChange={(e) => setStartLocal(e.target.value)}
          />
        </Field>
        <Field label="Duration (min)">
          <Input
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            inputMode="numeric"
          />
        </Field>
      </div>

      {/* Dentists */}
      <div className="grid grid-cols-2 gap-4">
        <Field label="Primary dentist">
          <select
            value={dentistId}
            onChange={(e) => setDentistId(e.target.value)}
            className={controlClass}
          >
            <option value="">— unassigned —</option>
            {dentistOptions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Consulting dentist">
          <select
            value={consultingId}
            onChange={(e) => setConsultingId(e.target.value)}
            className={controlClass}
          >
            <option value="">— none —</option>
            {dentistOptions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">
        The consulting dentist is optional — set it only when a second dentist takes over the treatment.
      </p>

      <Field label="Reason">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. toothache, check-up" />
      </Field>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Booking…" : "Book appointment"}
        </Button>
        <Link href="/calendar" className={buttonVariants({ variant: "outline" })}>
          Cancel
        </Link>
      </div>
    </form>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">
        {label}
        {required && <span className="text-destructive"> *</span>}
      </span>
      {children}
    </label>
  );
}
