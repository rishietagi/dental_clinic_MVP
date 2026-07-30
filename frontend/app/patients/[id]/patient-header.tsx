"use client";

// The patient header (6.8) — the "what do I need to know / do about this person
// right now" strip that sits above the profile tabs.
//
// Before 6.8 the profile was one long column whose only outbound link was back
// to the patient list: to book, you went to the calendar; to bill, you scrolled
// to a visit and hoped there was a link; the balance owed existed nowhere at
// all. This puts the three answers a receptionist actually needs — when are
// they next in, what do they owe, what can I do now — in one place.

import { useState } from "react";
import Link from "next/link";
import { CalendarPlus, IndianRupee, Stethoscope } from "lucide-react";

import { MedicalNotesBanner } from "@/components/medical-notes-banner";
import { buttonVariants } from "@/components/ui/button";
import { formatMoney } from "@/lib/use-invoices";
import { formatVisitDate } from "@/lib/use-visits";
import type { AppointmentListItem } from "@/lib/use-day-appointments";
import type { Patient } from "@/lib/use-patient";

// "Which appointment is next" depends on the current time. Reading the clock
// during render is impure (React may re-render at any moment and get a
// different answer) and would also risk a server/client hydration mismatch.
//
// So the clock is read ONCE on mount via a lazy initialiser, and the answer is
// then derived purely from that fixed instant. No setState in an effect (the
// 6.2 house rule) and no impure call in the render path — and "now" being
// pinned to page load is exactly right for a profile you glance at.
function useNextAppointment(appointments: AppointmentListItem[]): string | null {
  const [now] = useState(() => Date.now());

  // The list arrives newest-first, so the soonest future one is last.
  const future = appointments.filter(
    (a) =>
      new Date(a.start_time).getTime() > now &&
      a.status !== "cancelled" &&
      a.status !== "no_show",
  );
  return future.length ? future[future.length - 1].start_time : null;
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "danger";
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={`text-sm font-medium tabular-nums ${
          tone === "danger" ? "text-danger" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}

export function PatientHeader({
  patient,
  appointments,
  outstanding,
  lastVisit,
  canManage,
}: {
  patient: Patient;
  appointments: AppointmentListItem[];
  outstanding: string;
  lastVisit: string | null;
  canManage: boolean;
}) {
  const nextAppointment = useNextAppointment(appointments);
  const owes = Number(outstanding) > 0;

  return (
    <div className="flex flex-col gap-4">
      <MedicalNotesBanner notes={patient.medical_notes} />

      <div className="rounded-xl border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              {patient.name}
              {patient.archived && (
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">
                  archived
                </span>
              )}
            </h1>
            <p className="text-sm text-muted-foreground">
              {[
                patient.phone,
                patient.age !== null ? `${patient.age} yrs` : null,
                patient.gender,
              ]
                .filter(Boolean)
                .join(" · ") || "No contact details"}
            </p>
          </div>

          {/* The actions that were previously scattered or missing entirely. */}
          {!patient.archived && (
            <div className="flex flex-wrap gap-2">
              <Link
                href={`/appointments/new?patient=${patient.id}`}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <CalendarPlus className="size-4" /> Book appointment
              </Link>
              {canManage && (
                <Link
                  href={`/patients/${patient.id}/visits/new`}
                  className={buttonVariants({ size: "sm" })}
                >
                  <Stethoscope className="size-4" /> Record visit
                </Link>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-10 gap-y-3 border-t pt-3">
          <Stat
            label="Outstanding"
            value={formatMoney(outstanding)}
            tone={owes ? "danger" : undefined}
          />
          <Stat
            label="Next appointment"
            value={nextAppointment ? formatVisitDate(nextAppointment) : "None booked"}
          />
          <Stat
            label="Last visit"
            value={lastVisit ? formatVisitDate(lastVisit) : "—"}
          />
          {owes && (
            <div className="ml-auto self-end">
              <Link
                href={`/invoices?patient=${patient.id}`}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <IndianRupee className="size-4" /> Settle bill
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
