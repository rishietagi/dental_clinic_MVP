"use client";

// The day-view calendar: one day's appointments, with date navigation.
//
// Read-only this step (3.3) — display + Prev/Today/Next + a date picker. Booking,
// status changes, week view and drag-drop come in later steps. Rows link to the
// patient profile.

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  changeStatus,
  nextStatuses,
  statusLabel,
  statusStyle,
  type Status,
} from "@/lib/appointment-status";
import { useDayAppointments, type AppointmentListItem } from "@/lib/use-day-appointments";

// A date as YYYY-MM-DD in the *browser's* local zone (what the date input uses).
function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// Step a YYYY-MM-DD string by whole days (parsed as local noon to dodge DST edges).
function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + days, 12, 0, 0);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

// HH:MM–HH:MM in the browser's locale, from an ISO start + a minute duration.
function timeRange(startIso: string, durationMin: number): string {
  const start = new Date(startIso);
  const end = new Date(start.getTime() + durationMin * 60_000);
  const fmt = (dt: Date) =>
    dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${fmt(start)}–${fmt(end)}`;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${statusStyle(status)}`}>
      {statusLabel(status)}
    </span>
  );
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
  const [date, setDate] = useState<string>(todayIso());
  const state = useDayAppointments(date);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setDate(addDays(date, -1))}>
          ← Prev
        </Button>
        <Button variant="outline" size="sm" onClick={() => setDate(todayIso())}>
          Today
        </Button>
        <Button variant="outline" size="sm" onClick={() => setDate(addDays(date, 1))}>
          Next →
        </Button>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value || todayIso())}
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
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="px-3 py-2">{a.reason ?? "—"}</td>
                      <td className="px-3 py-2">
                        <StatusActions
                          appt={a}
                          onChanged={state.refetch}
                          onNotice={setNotice}
                        />
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
