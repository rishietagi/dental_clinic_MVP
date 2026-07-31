"use client";

// Register-a-patient form (6.3). Only the name is required (matching PatientCreate);
// phone/DOB/gender/medical notes are optional. On success it routes straight to the
// new patient's profile so the next step (book / record) is one click away.

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createPatient } from "@/lib/use-patients";

const controlClass =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

export function NewPatientForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState("");
  // "S/O" on the OPD card (6.10) — paediatric patients need a guardian.
  const [guardian, setGuardian] = useState("");
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (name.trim() === "") {
      setError("A patient name is required.");
      return;
    }
    setBusy(true);
    const result = await createPatient({
      name: name.trim(),
      phone: phone.trim() || null,
      date_of_birth: dob || null,
      gender: gender || null,
      guardian_name: guardian.trim() || null,
      address: address.trim() || null,
      medical_notes: notes.trim() || null,
    });
    setBusy(false);
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    toast.success("Patient registered");
    router.push(`/patients/${result.id}`);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Name" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </Field>
      <Field label="Phone">
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Date of birth">
          <Input type="date" value={dob} onChange={(e) => setDob(e.target.value)} />
        </Field>
        <Field label="Gender">
          <select
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            className={controlClass}
          >
            <option value="">—</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </select>
        </Field>
      </div>
      <Field label="Parent / guardian">
        <Input
          value={guardian}
          onChange={(e) => setGuardian(e.target.value)}
          placeholder="For a child or dependent patient"
        />
      </Field>
      <Field label="Address">
        <Input value={address} onChange={(e) => setAddress(e.target.value)} />
      </Field>
      <Field label="Medical notes">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Allergies, conditions, blood thinners… shown as a banner on the profile."
          className={controlClass}
        />
      </Field>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Register patient"}
        </Button>
        <Link href="/patients" className={buttonVariants({ variant: "outline" })}>
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
