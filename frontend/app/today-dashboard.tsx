"use client";

// Dashboard: today's schedule + an arrivals summary (3.6, restyled 6.4).
//
// Always "today" — the calendar browses other days. Clicking an appointment ROW
// routes to the chairside/visit screen (record consult → draft invoice); the
// patient-name link still opens the profile. Status changes live in the calendar's
// day view (one place owns them).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { StatusPill, type Tone } from "@/components/ui/status-pill";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { statusLabel, STATUSES } from "@/lib/appointment-status";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { useDayAppointments, type AppointmentListItem } from "@/lib/use-day-appointments";
import { fmtTimeInZone, todayIso } from "@/lib/week";

function timeRange(startIso: string, durationMin: number, tz: string): string {
  const endIso = new Date(new Date(startIso).getTime() + durationMin * 60_000).toISOString();
  return `${fmtTimeInZone(startIso, tz)}–${fmtTimeInZone(endIso, tz)}`;
}

// Appointment status → a semantic pill tone.
function apptTone(status: string): Tone {
  if (status === "done") return "good";
  if (status === "arrived") return "accent";
  if (status === "no_show" || status === "cancelled") return "danger";
  return "neutral"; // booked
}

function SummaryTile({ label, count, highlight }: { label: string; count: number; highlight?: boolean }) {
  return (
    <div className="rounded-xl border bg-card px-3.5 py-2.5">
      <div className={`text-2xl font-semibold tabular-nums ${highlight ? "text-primary" : ""}`}>
        {count}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function TodayDashboard() {
  const { settings } = useClinicSettings();
  const tz = settings.timezone;
  const today = todayIso(tz);
  const state = useDayAppointments(today);
  const router = useRouter();

  const items: AppointmentListItem[] = state.kind === "ready" ? state.data.items : [];
  const counts = Object.fromEntries(
    STATUSES.map((s) => [s, items.filter((a) => a.status === s).length]),
  ) as Record<(typeof STATUSES)[number], number>;

  return (
    <section className="flex w-full flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Today’s schedule</h2>
        <Link
          href="/calendar"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          View calendar <ArrowRight className="size-3.5" />
        </Link>
      </div>

      {state.kind === "loading" && <SkeletonRows rows={5} />}
      {state.kind === "error" && (
        <ErrorState message={`Couldn’t load today’s appointments: ${state.message}`} />
      )}

      {state.kind === "ready" && (
        <>
          <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-6">
            <SummaryTile label="Total" count={state.data.total} highlight />
            {STATUSES.map((s) => (
              <SummaryTile key={s} label={statusLabel(s)} count={counts[s]} />
            ))}
          </div>

          {items.length === 0 ? (
            <EmptyState title="No appointments today" hint="A quiet day — or time to schedule one." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Patient</TableHead>
                    <TableHead>Dentist</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((a) => (
                    <TableRow
                      key={a.id}
                      className="cursor-pointer"
                      onClick={() => router.push(`/patients/${a.patient_id}/visits/new?appointment=${a.id}`)}
                    >
                      <TableCell className="whitespace-nowrap tabular-nums">
                        {timeRange(a.start_time, a.duration_min, tz)}
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/patients/${a.patient_id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-primary hover:underline"
                        >
                          {a.patient_name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        {a.dentist_name ?? "—"}
                        {a.consulting_dentist_name && (
                          <span className="block text-xs text-muted-foreground">
                            + {a.consulting_dentist_name}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusPill tone={apptTone(a.status)}>{statusLabel(a.status)}</StatusPill>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{a.reason ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
