"use client";

// The dashboard's lab card (6.6) — two short lists that stop a case being forgotten:
//
//   1. "Due back" — what's still at the lab, OVERDUE first and in red. This is the
//      case nobody chased.
//   2. "Back from lab — call the patient in" — work that has returned but the patient
//      hasn't been booked to have it fitted. The lifecycle is deliberately just
//      sent→received, so this list (cleared by the Done button) is what replaces a
//      "fitted" state.
//
// Hidden entirely when there's nothing to show, so a quiet day stays quiet.

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import {
  daysUntil,
  dismissFollowUp,
  duePhrase,
  formatCaseNumber,
  sampleTypeLabel,
  useLabDashboard,
  type LabCase,
} from "@/lib/use-lab-cases";
import { cn } from "@/lib/utils";

export function LabDashboardCard() {
  const state = useLabDashboard();

  if (state.kind === "loading") return null;
  if (state.kind === "error") {
    return <ErrorState message={`Couldn’t load lab work: ${state.message}`} />;
  }

  const { overdue, due_soon, back_from_lab } = state.data;
  const pending = [...overdue, ...due_soon];
  if (pending.length === 0 && back_from_lab.length === 0) return null;

  return (
    <section className="flex w-full flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Lab work</h2>
        <Link href="/lab" className="text-sm text-muted-foreground hover:text-foreground">
          View all lab work →
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {pending.length > 0 && (
          <div className="rounded-xl border bg-card p-4">
            <h3 className="mb-2 text-sm font-medium">Due back</h3>
            <ul className="flex flex-col divide-y">
              {pending.map((c) => (
                <PendingRow key={c.id} labCase={c} />
              ))}
            </ul>
          </div>
        )}

        {back_from_lab.length > 0 && (
          <div className="rounded-xl border bg-card p-4">
            <h3 className="mb-2 text-sm font-medium">Back from lab — call the patient in</h3>
            <ul className="flex flex-col divide-y">
              {back_from_lab.map((c) => (
                <BackRow key={c.id} labCase={c} onChanged={state.refetch} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

function PendingRow({ labCase: c }: { labCase: LabCase }) {
  const days = daysUntil(c.expected_date);
  const overdue = days !== null && days < 0;

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <Link href={`/patients/${c.patient_id}`} className="font-medium hover:underline">
          {c.patient_name}
        </Link>
        <span className="ml-2 text-sm text-muted-foreground">
          {sampleTypeLabel(c.sample_type)} · {c.lab_name}
        </span>
      </div>
      <span
        className={cn(
          "whitespace-nowrap text-sm",
          overdue ? "font-medium text-danger" : "text-muted-foreground",
        )}
      >
        {duePhrase(c.expected_date)}
      </span>
    </li>
  );
}

function BackRow({ labCase: c, onChanged }: { labCase: LabCase; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);

  async function done() {
    setBusy(true);
    const result = await dismissFollowUp(c.id, true);
    setBusy(false);
    if (result.status === "error") {
      toast.error(result.message);
      return;
    }
    toast.success(`${formatCaseNumber(c.number)} — patient called in`);
    onChanged();
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <Link href={`/patients/${c.patient_id}`} className="font-medium hover:underline">
          {c.patient_name}
        </Link>
        <span className="ml-2 text-sm text-muted-foreground">
          {sampleTypeLabel(c.sample_type)}
        </span>
        <StatusPill tone="good" className="ml-2">
          Ready
        </StatusPill>
      </div>
      <Button variant="outline" size="sm" disabled={busy} onClick={done}>
        Done
      </Button>
    </li>
  );
}
