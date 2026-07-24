"use client";

// The Invoices ledger table (6.4). Lists every invoice with the patient, date,
// total, paid, outstanding, and a status pill; a status filter; each row links to
// the invoice. Uses the shadcn Table + shared state components.

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusPill, type Tone } from "@/components/ui/status-pill";
import { formatMoney, statusLabel, useInvoiceList } from "@/lib/use-invoices";
import { formatVisitDate } from "@/lib/use-visits";
import { cn } from "@/lib/utils";

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "unpaid", label: "Unpaid" },
  { value: "partially_paid", label: "Partial" },
  { value: "paid", label: "Paid" },
];

function statusTone(status: string): Tone {
  if (status === "paid") return "good";
  if (status === "partially_paid") return "warning";
  return "neutral";
}

export function InvoicesList() {
  const [filter, setFilter] = useState("");
  const state = useInvoiceList(filter || undefined);
  const router = useRouter();

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

      {state.kind === "loading" && <SkeletonRows rows={6} />}
      {state.kind === "error" && (
        <ErrorState message={`Couldn’t load invoices: ${state.message}`} />
      )}
      {state.kind === "ready" && state.items.length === 0 && (
        <EmptyState
          title="No invoices yet"
          hint="Invoices you generate from a visit will appear here."
        />
      )}

      {state.kind === "ready" && state.items.length > 0 && (
        <div className="rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Patient</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead className="text-right">Outstanding</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.items.map((inv) => (
                <TableRow
                  key={inv.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`/invoices/${inv.id}`)}
                >
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {formatVisitDate(inv.created_at)}
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/patients/${inv.patient_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-medium text-primary hover:underline"
                    >
                      {inv.patient_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatMoney(inv.total)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {formatMoney(inv.amount_paid)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {formatMoney(inv.outstanding)}
                  </TableCell>
                  <TableCell>
                    <StatusPill tone={statusTone(inv.status)}>{statusLabel(inv.status)}</StatusPill>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
