"use client";

// "Send to lab" (6.6) — the form that creates a lab case.
//
// Reached three ways, all landing here so there's ONE form to learn:
//   /lab/new                                   (from the Lab tab)
//   /lab/new?patient=<id>&name=...             (from a patient)
//   /lab/new?patient=<id>&appointment=<id>     (from the calendar)
//   /lab/new?patient=<id>&visit=<id>           (from a recorded visit)
// Anything supplied in the query is prefilled and the patient search is skipped.
//
// Beginner-friendly choices: sent date defaults to today, expected date defaults to
// a week out (the usual lab turnaround), sample type and lab are dropdowns, and a
// new lab can be added inline without leaving the page.

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createLab, useLabs } from "@/lib/use-labs";
import {
  createLabCase,
  SAMPLE_TYPES,
  sampleTypeLabel,
} from "@/lib/use-lab-cases";
import { usePatientSearch } from "@/lib/use-patient-search";

const controlClass =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isoInDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function SendToLabForm() {
  const router = useRouter();
  const params = useSearchParams();

  const seededPatientId = params.get("patient");
  const seededName = params.get("name");
  const visitId = params.get("visit");
  const appointmentId = params.get("appointment");

  const [patient, setPatient] = useState<{ id: string; name: string } | null>(
    seededPatientId ? { id: seededPatientId, name: seededName ?? "Selected patient" } : null,
  );
  const [query, setQuery] = useState("");
  const search = usePatientSearch(query);

  const labs = useLabs();
  const [labId, setLabId] = useState("");
  const [sampleType, setSampleType] = useState<string>("crown");
  const [tooth, setTooth] = useState("");
  const [sentDate, setSentDate] = useState(isoToday());
  const [expectedDate, setExpectedDate] = useState(isoInDays(7));
  const [notes, setNotes] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inline "add a lab" so the receptionist never has to go to Settings mid-task.
  const [showAddLab, setShowAddLab] = useState(false);
  const [newLabName, setNewLabName] = useState("");
  const [newLabPhone, setNewLabPhone] = useState("");

  const labOptions = labs.kind === "ready" ? labs.items : [];

  async function addLab() {
    if (!newLabName.trim()) return;
    setBusy(true);
    const result = await createLab({ name: newLabName.trim(), phone: newLabPhone.trim() || undefined });
    setBusy(false);
    if (result.status === "forbidden") {
      toast.error("Only an admin can add a lab. Ask an admin to add it in Settings.");
      return;
    }
    if (result.status === "error") {
      toast.error(result.message);
      return;
    }
    toast.success(`${result.lab.name} added`);
    setLabId(result.lab.id);
    setNewLabName("");
    setNewLabPhone("");
    setShowAddLab(false);
    labs.refetch();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!patient) {
      setError("Choose a patient first.");
      return;
    }
    if (!labId) {
      setError("Choose which lab this is going to.");
      return;
    }
    if (expectedDate && expectedDate < sentDate) {
      setError("The expected date can’t be before the sent date.");
      return;
    }

    setBusy(true);
    const result = await createLabCase({
      patient_id: patient.id,
      lab_id: labId,
      sample_type: sampleType,
      sent_date: sentDate,
      expected_date: expectedDate || null,
      visit_id: visitId,
      appointment_id: appointmentId,
      tooth_ref: tooth.trim() || null,
      notes: notes.trim() || null,
    });
    setBusy(false);

    if (result.status === "error") {
      setError(result.message);
      return;
    }
    toast.success(`Sent to lab — case L-${result.case.number}`);
    router.push("/lab");
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Send to lab</h1>
        <Link href="/lab" className={buttonVariants({ variant: "outline", size: "sm" })}>
          Back to lab work
        </Link>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        {/* Patient — skipped entirely when we arrived with one. */}
        <Card>
          <CardHeader>
            <CardTitle>Patient</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {patient ? (
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium">{patient.name}</span>
                {!seededPatientId && (
                  <Button type="button" variant="outline" size="sm" onClick={() => setPatient(null)}>
                    Change
                  </Button>
                )}
              </div>
            ) : (
              <>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by name or phone…"
                  aria-label="Search patients"
                />
                {search.kind === "ready" && search.data.items.length > 0 && (
                  <ul className="flex flex-col divide-y rounded-md border">
                    {search.data.items.slice(0, 6).map((p) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          onClick={() => setPatient({ id: p.id, name: p.name })}
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
                        >
                          <span className="font-medium">{p.name}</span>
                          <span className="text-muted-foreground">{p.phone ?? "—"}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* The case itself. */}
        <Card>
          <CardHeader>
            <CardTitle>The work</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-1 flex-col gap-1">
                <label className="text-xs text-muted-foreground">What is being made</label>
                <select
                  value={sampleType}
                  onChange={(e) => setSampleType(e.target.value)}
                  className={controlClass}
                >
                  {SAMPLE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {sampleTypeLabel(t)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex w-28 flex-col gap-1">
                <label className="text-xs text-muted-foreground">Tooth (optional)</label>
                <Input value={tooth} onChange={(e) => setTooth(e.target.value)} placeholder="36" />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Which lab</label>
              <select
                value={labId}
                onChange={(e) => setLabId(e.target.value)}
                className={controlClass}
              >
                <option value="">Choose a lab…</option>
                {labOptions.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
              {!showAddLab ? (
                <button
                  type="button"
                  onClick={() => setShowAddLab(true)}
                  className="mt-1 w-fit text-xs text-primary underline"
                >
                  + Add a new lab
                </button>
              ) : (
                <div className="mt-2 flex flex-wrap items-end gap-2 rounded-md border p-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Lab name</label>
                    <Input value={newLabName} onChange={(e) => setNewLabName(e.target.value)} className="w-52" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Phone</label>
                    <Input value={newLabPhone} onChange={(e) => setNewLabPhone(e.target.value)} className="w-40" />
                  </div>
                  <Button type="button" size="sm" disabled={busy} onClick={addLab}>
                    Add
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setShowAddLab(false)}>
                    Cancel
                  </Button>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-4">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">Sent on</label>
                <input
                  type="date"
                  value={sentDate}
                  onChange={(e) => setSentDate(e.target.value)}
                  className={`${controlClass} w-44`}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">Expected back</label>
                <input
                  type="date"
                  value={expectedDate}
                  onChange={(e) => setExpectedDate(e.target.value)}
                  className={`${controlClass} w-44`}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Notes (optional)</label>
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Shade A2, patient wants it before the wedding…"
              />
            </div>
          </CardContent>
        </Card>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div>
          <Button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Send to lab"}
          </Button>
        </div>
      </form>
    </div>
  );
}
