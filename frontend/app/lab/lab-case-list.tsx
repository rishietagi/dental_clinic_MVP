"use client";

// The lab case table (6.6). Filter chips across the top, one row per case with the
// readable numbers (L-1042 / A-1007), and the two actions the receptionist needs:
// "Mark received" when the box comes back, and "Cancel" for a scrapped case.
//
// Overdue rows are called out in red with a plain phrase ("3 days overdue") rather
// than making her compare dates herself — that's the whole reason this screen exists.

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { StatusPill, type Tone } from "@/components/ui/status-pill";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  cancelLabCase,
  daysUntil,
  duePhrase,
  formatApptNumber,
  formatCaseNumber,
  labStatusLabel,
  markReceived,
  sampleTypeLabel,
  useLabCases,
  type LabCase,
} from "@/lib/use-lab-cases";
import { formatVisitDate } from "@/lib/use-visits";
import { cn } from "@/lib/utils";

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "sent", label: "At the lab" },
  { value: "received", label: "Back from lab" },
  { value: "cancelled", label: "Cancelled" },
];

function statusTone(status: string): Tone {
  if (status === "received") return "good";
  if (status === "cancelled") return "neutral";
  return "accent"; // sent — in flight
}

export function LabCaseList({ patientId }: { patientId?: string } = {}) {
  const [filter, setFilter] = useState("");
  const state = useLabCases({ status: filter || undefined, patientId });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setFilter(f.value)}
            className={cn(
              "rounded-full px-3 py-1 text-sm transition-colors",
              filter === f.value
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {state.kind === "loading" && <SkeletonRows rows={5} />}
      {state.kind === "error" && (
        <ErrorState message={`Couldn’t load lab work: ${state.message}`} />
      )}
      {state.kind === "ready" && state.items.length === 0 && (
        <EmptyState
          title="Nothing here yet"
          hint="Samples you send to a lab will show up here, with what's due back."
        />
      )}

      {state.kind === "ready" && state.items.length > 0 && (
        <div className="rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case</TableHead>
                <TableHead>Patient</TableHead>
                <TableHead>Appointment</TableHead>
                <TableHead>Work</TableHead>
                <TableHead>Lab</TableHead>
                <TableHead>Sent</TableHead>
                <TableHead>Expected</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.items.map((c) => (
                <CaseRow key={c.id} labCase={c} onChanged={state.refetch} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function CaseRow({ labCase: c, onChanged }: { labCase: LabCase; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const atLab = c.status === "sent";
  const days = daysUntil(c.expected_date);
  const overdue = atLab && days !== null && days < 0;

  async function receive() {
    setBusy(true);
    const result = await markReceived(c.id);
    setBusy(false);
    if (result.status === "error") {
      toast.error(result.message);
      return;
    }
    toast.success(`${formatCaseNumber(c.number)} marked back from the lab`);
    onChanged();
  }

  async function cancel() {
    setBusy(true);
    const result = await cancelLabCase(c.id);
    setBusy(false);
    if (result.status === "error") {
      toast.error(result.message);
      return;
    }
    toast.success(`${formatCaseNumber(c.number)} cancelled`);
    onChanged();
  }

  return (
    <TableRow className={c.status === "cancelled" ? "opacity-60" : ""}>
      <TableCell className="font-medium tabular-nums">{formatCaseNumber(c.number)}</TableCell>
      <TableCell>
        <Link href={`/patients/${c.patient_id}`} className="font-medium text-primary hover:underline">
          {c.patient_name}
        </Link>
      </TableCell>
      <TableCell className="tabular-nums text-muted-foreground">
        {formatApptNumber(c.appointment_number)}
      </TableCell>
      <TableCell>
        {sampleTypeLabel(c.sample_type)}
        {c.tooth_ref && <span className="text-muted-foreground"> · tooth {c.tooth_ref}</span>}
      </TableCell>
      <TableCell className="text-muted-foreground">{c.lab_name}</TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {formatVisitDate(c.sent_date)}
      </TableCell>
      <TableCell className="whitespace-nowrap">
        {c.expected_date ? (
          <>
            {formatVisitDate(c.expected_date)}
            {atLab && (
              <span className={cn("block text-xs", overdue ? "text-danger font-medium" : "text-muted-foreground")}>
                {duePhrase(c.expected_date)}
              </span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <StatusPill tone={overdue ? "danger" : statusTone(c.status)}>
          {overdue ? "Overdue" : labStatusLabel(c.status)}
        </StatusPill>
      </TableCell>
      <TableCell className="text-right">
        {atLab ? (
          <div className="flex justify-end gap-1">
            <Button size="sm" disabled={busy} onClick={receive}>
              Mark received
            </Button>
            <Button variant="outline" size="sm" disabled={busy} onClick={cancel}>
              Cancel
            </Button>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">
            {c.received_date ? `Back ${formatVisitDate(c.received_date)}` : "—"}
          </span>
        )}
      </TableCell>
    </TableRow>
  );
}
