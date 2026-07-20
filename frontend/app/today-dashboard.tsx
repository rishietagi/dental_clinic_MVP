"use client";

// Dashboard v1 (step 3.6): today's schedule + an arrivals summary.
//
// Always "today" — no date navigation (the calendar is for browsing other days).
// Reuses the day-list hook and the status labels/colours rather than duplicating
// them. Status changes are NOT here: those live in the calendar's day view, so
// there's one place that owns them.

import Link from "next/link";

import { statusLabel, statusStyle, STATUSES } from "@/lib/appointment-status";
import { useDayAppointments, type AppointmentListItem } from "@/lib/use-day-appointments";
import { todayIso } from "@/lib/week";

// HH:MM–HH:MM in the browser's locale, from an ISO start + a minute duration.
function timeRange(startIso: string, durationMin: number): string {
  const start = new Date(startIso);
  const end = new Date(start.getTime() + durationMin * 60_000);
  const fmt = (dt: Date) =>
    dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${fmt(start)}–${fmt(end)}`;
}

function SummaryTile({
  label,
  count,
  className = "",
}: {
  label: string;
  count: number;
  className?: string;
}) {
  return (
    <div className={`rounded-lg border px-3 py-2 ${className}`}>
      <div className="text-xl font-semibold tabular-nums">{count}</div>
      <div className="text-xs">{label}</div>
    </div>
  );
}

export function TodayDashboard() {
  const today = todayIso();
  const state = useDayAppointments(today);

  const items: AppointmentListItem[] = state.kind === "ready" ? state.data.items : [];
  // Counts per status, derived from the same list the table renders.
  const counts = Object.fromEntries(
    STATUSES.map((s) => [s, items.filter((a) => a.status === s).length]),
  ) as Record<(typeof STATUSES)[number], number>;

  return (
    <section className="flex w-full flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Today’s schedule</h2>
        <Link href="/calendar" className="text-sm text-muted-foreground hover:underline">
          View calendar →
        </Link>
      </div>

      {state.kind === "loading" && (
        <p className="text-sm text-muted-foreground">Loading today’s appointments…</p>
      )}

      {state.kind === "error" && (
        <p className="text-sm text-destructive">
          Couldn’t load today’s appointments: {state.message}
        </p>
      )}

      {state.kind === "ready" && (
        <>
          {/* Arrivals summary — at a glance, who's in and what's left. */}
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            <SummaryTile label="Total" count={state.data.total} />
            {STATUSES.map((s) => (
              <SummaryTile
                key={s}
                label={statusLabel(s)}
                count={counts[s]}
                className={statusStyle(s)}
              />
            ))}
          </div>

          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No appointments today.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/50 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Time</th>
                    <th className="px-3 py-2 font-medium">Patient</th>
                    <th className="px-3 py-2 font-medium">Dentist</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((a) => (
                    <tr key={a.id} className="border-b last:border-0">
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                        {timeRange(a.start_time, a.duration_min)}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          href={`/patients/${a.patient_id}`}
                          className="font-medium hover:underline"
                        >
                          {a.patient_name}
                        </Link>
                      </td>
                      <td className="px-3 py-2">{a.dentist_name ?? "—"}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs ${statusStyle(a.status)}`}
                        >
                          {statusLabel(a.status)}
                        </span>
                      </td>
                      <td className="px-3 py-2">{a.reason ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
