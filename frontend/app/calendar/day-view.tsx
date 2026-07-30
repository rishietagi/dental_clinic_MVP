"use client";

// The day-view calendar: one day's appointments, with date navigation.
//
// Read-only this step (3.3) — display + Prev/Today/Next + a date picker. Booking,
// status changes, week view and drag-drop come in later steps. Rows link to the
// patient profile.

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusPill, type Tone } from "@/components/ui/status-pill";
import {
  changeStatus,
  nextStatuses,
  statusLabel,
  type Status,
} from "@/lib/appointment-status";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { useDayAppointments, type AppointmentListItem } from "@/lib/use-day-appointments";
import { fmtTimeInZone, todayIso } from "@/lib/week";

// Step a YYYY-MM-DD string by whole days (parsed as local noon to dodge DST edges).
function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + days, 12, 0, 0);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

// HH:MM–HH:MM in the CLINIC zone, from an ISO start + a minute duration.
function timeRange(startIso: string, durationMin: number, tz: string): string {
  const endIso = new Date(new Date(startIso).getTime() + durationMin * 60_000).toISOString();
  return `${fmtTimeInZone(startIso, tz)}–${fmtTimeInZone(endIso, tz)}`;
}

function apptTone(status: string): Tone {
  if (status === "done") return "good";
  if (status === "arrived") return "accent";
  if (status === "no_show" || status === "cancelled") return "danger";
  return "neutral";
}

function StatusBadge({ status }: { status: string }) {
  return <StatusPill tone={apptTone(status)}>{statusLabel(status)}</StatusPill>;
}

// The legal next-status buttons for one appointment. Terminal statuses render
// nothing. A 409 (someone else already moved it) shows a note and refreshes.
function StatusActions({
  appt,
  onChanged,
  onNotice,
}: {
  appt: AppointmentListItem;
  onChanged: () => void;
  onNotice: (msg: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const options = nextStatuses(appt.status);
  if (options.length === 0) return <span className="text-muted-foreground">—</span>;

  async function apply(target: Status) {
    setBusy(true);
    const result = await changeStatus(appt.id, target);
    setBusy(false);
    if (result === "ok") {
      onChanged();
    } else if (result === "conflict") {
      onNotice("That change was no longer valid — refreshed.");
      onChanged();
    } else {
      onNotice(result.error);
    }
  }

  return (
    <div className="flex flex-wrap gap-1">
      {options.map((target) => (
        <Button
          key={target}
          variant="outline"
          size="xs"
          disabled={busy}
          onClick={() => apply(target)}
        >
          {statusLabel(target)}
        </Button>
      ))}
    </div>
  );
}

export function DayView() {
  const { settings } = useClinicSettings();
  const tz = settings.timezone;
  const [date, setDate] = useState<string>(() => todayIso(tz));
  const state = useDayAppointments(date);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setDate(addDays(date, -1))}>
          ← Prev
        </Button>
        <Button variant="outline" size="sm" onClick={() => setDate(todayIso(tz))}>
          Today
        </Button>
        <Button variant="outline" size="sm" onClick={() => setDate(addDays(date, 1))}>
          Next →
        </Button>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value || todayIso(tz))}
          aria-label="Pick a date"
          className="ml-1 rounded-md border bg-background px-2 py-1 text-sm"
        />
      </div>

      {notice && <p className="text-sm text-destructive">{notice}</p>}

      {state.kind === "loading" && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {state.kind === "error" && (
        <p className="text-sm text-destructive">
          Couldn’t load appointments: {state.message}
        </p>
      )}

      {state.kind === "ready" && (
        <>
          <p className="text-sm text-muted-foreground">
            {state.data.total}{" "}
            {state.data.total === 1 ? "appointment" : "appointments"}
          </p>

          {state.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No appointments on this day.
            </p>
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
                    <th className="px-3 py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((a: AppointmentListItem) => (
                    <tr key={a.id} className="border-b last:border-0">
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                        {timeRange(a.start_time, a.duration_min, tz)}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          href={`/patients/${a.patient_id}`}
                          className="font-medium hover:underline"
                        >
                          {a.patient_name}
                        </Link>
                      </td>
                      <td className="px-3 py-2">
                        {a.dentist_name ?? "—"}
                        {a.consulting_dentist_name && (
                          <span className="block text-xs text-muted-foreground">
                            + {a.consulting_dentist_name}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="px-3 py-2">{a.reason ?? "—"}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col items-start gap-1">
                          <StatusActions
                            appt={a}
                            onChanged={state.refetch}
                            onNotice={setNotice}
                          />
                          <Link
                            href={`/patients/${a.patient_id}/visits/new?appointment=${a.id}`}
                            className="text-xs font-medium text-primary hover:underline"
                          >
                            Start visit →
                          </Link>
                          {/* Impressions often go out at the appointment itself, so
                              the send form is reachable straight from the row. */}
                          <Link
                            href={`/lab/new?patient=${a.patient_id}&appointment=${a.id}&name=${encodeURIComponent(a.patient_name)}`}
                            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                          >
                            Send to lab
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
