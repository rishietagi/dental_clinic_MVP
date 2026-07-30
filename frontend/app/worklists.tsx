"use client";

// Two dashboard worklists added in 6.8, both from the end-to-end walkthrough:
//
//   "To bill"          — visits with no invoice. Until now billing was reachable
//                        ONLY by clicking through from the visit you had just
//                        recorded; miss that moment and the work was invisible.
//                        The dev DB had 9 unbilled visits nobody could see.
//
//   "Nothing recorded" — appointments marked done with no clinical write-up.
//                        Genuinely ambiguous (treated? or forgotten?), so it is
//                        surfaced with a one-click way to fix it.
//
// Both hide themselves when empty, so a clinic that is up to date sees a clean
// dashboard rather than two empty boxes (the 6.6 lab-card rule).

import Link from "next/link";
import { IndianRupee, NotebookPen } from "lucide-react";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { formatVisitDate } from "@/lib/use-visits";
import { useMissingVisits, useUnbilledVisits } from "@/lib/use-worklists";

function CardShell({
  title,
  count,
  hint,
  icon,
  children,
}: {
  title: string;
  count: number;
  hint: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="flex w-full flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          {icon}
          {title}
          <span className="rounded-full bg-muted px-2 py-0.5 text-sm font-medium text-muted-foreground">
            {count}
          </span>
        </h2>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </div>
      <div className="overflow-x-auto rounded-lg border">{children}</div>
    </section>
  );
}

/** Visits that were carried out but never invoiced. */
export function ToBillCard() {
  const state = useUnbilledVisits();

  if (state.kind === "loading") return null;
  if (state.kind === "error") {
    return <ErrorState message={`Couldn’t load unbilled visits: ${state.message}`} />;
  }
  if (state.items.length === 0) return null;

  return (
    <CardShell
      title="Ready to bill"
      count={state.total}
      hint="Treatment recorded but not yet invoiced."
      icon={<IndianRupee className="size-5 text-muted-foreground" />}
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Patient</TableHead>
            <TableHead>Treatment</TableHead>
            <TableHead>Visit</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {state.items.slice(0, 8).map((v) => (
            <TableRow key={v.id}>
              <TableCell className="font-medium">
                <Link href={`/patients/${v.patient_id}`} className="hover:underline">
                  {v.patient_name}
                </Link>
              </TableCell>
              <TableCell>
                {v.treatment_title}
                {v.procedure_count > 0 && (
                  <span className="text-muted-foreground">
                    {" "}
                    · {v.procedure_count} item{v.procedure_count === 1 ? "" : "s"}
                  </span>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {formatVisitDate(v.visit_date)}
              </TableCell>
              <TableCell className="text-right">
                <Link href={`/invoices/new/${v.id}`}>
                  <Button size="xs">Create bill</Button>
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {state.total > 8 && (
        <p className="border-t px-3 py-2 text-xs text-muted-foreground">
          Showing 8 of {state.total}.
        </p>
      )}
    </CardShell>
  );
}

/** Appointments finished today with nothing written up. */
export function NothingRecordedCard() {
  const { settings } = useClinicSettings();
  // "Today" in the CLINIC's zone, not the browser's (the 4.9 rule) — an evening
  // appointment must not fall onto tomorrow's list for a late-working user.
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: settings.timezone,
  }).format(new Date());

  const state = useMissingVisits(today);

  if (state.kind === "loading") return null;
  if (state.kind === "error") return null; // a nudge is not worth an error banner
  if (state.items.length === 0) return null;

  return (
    <CardShell
      title="Nothing recorded"
      count={state.total}
      hint="Marked finished today, but no visit was written up."
      icon={<NotebookPen className="size-5 text-muted-foreground" />}
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Patient</TableHead>
            <TableHead>Reason</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {state.items.map((a) => (
            <TableRow key={a.id}>
              <TableCell className="font-medium">
                <Link href={`/patients/${a.patient_id}`} className="hover:underline">
                  {a.patient_name}
                </Link>
              </TableCell>
              <TableCell className="text-muted-foreground">{a.reason ?? "—"}</TableCell>
              <TableCell className="text-right">
                <Link
                  href={`/patients/${a.patient_id}/visits/new?appointment=${a.id}`}
                >
                  <Button size="xs" variant="outline">
                    Record now
                  </Button>
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CardShell>
  );
}
