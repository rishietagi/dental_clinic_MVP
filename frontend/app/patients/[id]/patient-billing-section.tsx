"use client";

// The patient profile's Billing tab (6.8).
//
// Before this, answering "what does this patient owe?" meant opening the
// clinic-wide invoice ledger and reading down it by eye — and the obvious
// shortcut, `GET /invoices?patient_id=`, silently returned EVERY invoice in the
// clinic because the param was never declared on the API. Both halves are fixed:
// the filter is real (6.8) and this is the screen that uses it.
//
// Deliberately a list of that patient's bills with a running total, not a
// second payment UI — taking payment stays on the invoice screen, one place.

import Link from "next/link";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatMoney, statusLabel, useInvoiceList } from "@/lib/use-invoices";
import { formatVisitDate } from "@/lib/use-visits";

const TONE: Record<string, "good" | "warning" | "danger"> = {
  paid: "good",
  partially_paid: "warning",
  unpaid: "danger",
};

export function PatientBillingSection({ patientId }: { patientId: string }) {
  const state = useInvoiceList(undefined, patientId);

  if (state.kind === "loading") return <LoadingState label="Loading bills…" />;
  if (state.kind === "error") {
    return <ErrorState message={`Couldn’t load bills: ${state.message}`} />;
  }
  if (state.items.length === 0) {
    return (
      <EmptyState
        title="No bills yet"
        hint="A bill is created from a recorded visit."
      />
    );
  }

  // Summed from the rows already fetched — no second request, and it cannot
  // disagree with the list it sits under.
  const billed = state.items.reduce((n, i) => n + Number(i.total), 0);
  const paid = state.items.reduce((n, i) => n + Number(i.amount_paid), 0);
  const outstanding = state.items.reduce((n, i) => n + Number(i.outstanding), 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-x-10 gap-y-2 rounded-lg border bg-muted/30 p-3 text-sm">
        <div>
          <span className="text-muted-foreground">Billed </span>
          <span className="font-medium tabular-nums">{formatMoney(String(billed))}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Paid </span>
          <span className="font-medium tabular-nums">{formatMoney(String(paid))}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Outstanding </span>
          <span
            className={`font-medium tabular-nums ${outstanding > 0 ? "text-danger" : ""}`}
          >
            {formatMoney(String(outstanding))}
          </span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="text-right">Paid</TableHead>
              <TableHead className="text-right">Outstanding</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {state.items.map((inv) => (
              <TableRow key={inv.id}>
                <TableCell className="text-muted-foreground">
                  {formatVisitDate(inv.created_at)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMoney(inv.total)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMoney(inv.amount_paid)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMoney(inv.outstanding)}
                </TableCell>
                <TableCell>
                  <StatusPill tone={TONE[inv.status] ?? "warning"}>
                    {statusLabel(inv.status)}
                  </StatusPill>
                </TableCell>
                <TableCell className="text-right">
                  <Link
                    href={`/invoices/${inv.id}`}
                    className={buttonVariants({ variant: "outline", size: "xs" })}
                  >
                    {Number(inv.outstanding) > 0 ? "Take payment" : "View"}
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
