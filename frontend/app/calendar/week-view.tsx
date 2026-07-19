"use client";

// The week-view calendar with drag-drop reschedule (3.4).
//
// A time grid: rows are 30-min slots (09:00–17:30), columns are the 7 days of the
// week. Appointments render as draggable cards in their (day, slot) cell; each
// cell is a drop target. Dropping a card PATCHes its start_time to that day+slot.
// A same-dentist overlap comes back 409 and is shown inline (the card stays put).
//
// Clinic hours + slot size are hardcoded (lib/week.ts) until Phase 4 clinic
// settings. Times are the browser's local zone (see the LOG timezone caveat).

import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { AppointmentListItem } from "@/lib/use-day-appointments";
import {
  useWeekAppointments,
  rescheduleAppointment,
} from "@/lib/use-week-appointments";
import {
  addWeeks,
  cellId,
  daySlots,
  fmtDayHeader,
  fmtSlot,
  parseCellId,
  slotDate,
  slotForStart,
  startOfWeek,
  todayIso,
  weekDays,
  type Slot,
} from "@/lib/week";

// ---- draggable appointment card --------------------------------------------

function ApptCard({ appt }: { appt: AppointmentListItem }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: appt.id,
    data: { appt },
  });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={`cursor-grab rounded border bg-background p-1 text-xs leading-tight shadow-sm ${
        isDragging ? "opacity-40" : ""
      }`}
    >
      <div className="font-medium">{appt.patient_name}</div>
      {appt.reason && <div className="truncate text-muted-foreground">{appt.reason}</div>}
    </div>
  );
}

// A non-interactive copy shown under the cursor while dragging.
function ApptCardOverlay({ appt }: { appt: AppointmentListItem }) {
  return (
    <div className="rounded border bg-background p-1 text-xs leading-tight shadow-md">
      <div className="font-medium">{appt.patient_name}</div>
      {appt.reason && <div className="truncate text-muted-foreground">{appt.reason}</div>}
    </div>
  );
}

// ---- droppable (day, slot) cell --------------------------------------------

function Cell({
  dayIso,
  slot,
  children,
}: {
  dayIso: string;
  slot: Slot;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: cellId(dayIso, slot) });
  return (
    <div
      ref={setNodeRef}
      className={`min-h-8 border-b border-l p-0.5 ${isOver ? "bg-accent" : ""}`}
    >
      {children}
    </div>
  );
}

// ---- the week view ----------------------------------------------------------

export function WeekView() {
  const [weekStart, setWeekStart] = useState<string>(startOfWeek(todayIso()));
  const state = useWeekAppointments(weekStart);
  const [dragging, setDragging] = useState<AppointmentListItem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // A small activation distance so a plain click still works as a link and only a
  // real drag starts a drag.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const days = weekDays(weekStart);
  const slots = daySlots();

  function onDragStart(event: DragStartEvent) {
    setNotice(null);
    setDragging((event.active.data.current?.appt as AppointmentListItem) ?? null);
  }

  async function onDragEnd(event: DragEndEvent) {
    const appt = dragging;
    setDragging(null);
    if (!appt || !event.over) return;

    const { dayIso, slot } = parseCellId(String(event.over.id));
    const newStart = slotDate(dayIso, slot);

    // No-op if dropped on its current slot.
    if (new Date(appt.start_time).getTime() === newStart.getTime()) return;

    const result = await rescheduleAppointment(appt.id, newStart.toISOString());
    if (result === "ok") {
      if ("refetch" in state) state.refetch();
    } else if (result === "conflict") {
      setNotice("That slot is already taken for this dentist.");
    } else {
      setNotice(result.error);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setWeekStart(addWeeks(weekStart, -1))}>
          ← Prev
        </Button>
        <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(todayIso()))}>
          This week
        </Button>
        <Button variant="outline" size="sm" onClick={() => setWeekStart(addWeeks(weekStart, 1))}>
          Next →
        </Button>
        <span className="ml-1 text-sm text-muted-foreground">
          Week of {days[0]}
        </span>
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
        <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
          <div className="overflow-x-auto rounded-lg border">
            {/* 1 time-axis column + 7 day columns */}
            <div className="grid min-w-[720px] grid-cols-[4rem_repeat(7,1fr)]">
              {/* header row */}
              <div className="border-b bg-muted/50 px-2 py-1 text-xs font-medium text-muted-foreground">
                Time
              </div>
              {days.map((d) => (
                <div
                  key={d}
                  className="border-b border-l bg-muted/50 px-2 py-1 text-center text-xs font-medium text-muted-foreground"
                >
                  {fmtDayHeader(d)}
                </div>
              ))}

              {/* slot rows */}
              {slots.map((slot) => (
                <FragmentRow key={fmtSlot(slot)}>
                  <div className="border-b px-2 py-1 text-right text-xs tabular-nums text-muted-foreground">
                    {fmtSlot(slot)}
                  </div>
                  {days.map((d) => {
                    const cardsHere = state.data.items.filter((a) => {
                      const s = slotForStart(a.start_time);
                      return (
                        s !== null &&
                        s.hour === slot.hour &&
                        s.minute === slot.minute &&
                        localDay(a.start_time) === d
                      );
                    });
                    return (
                      <Cell key={d + fmtSlot(slot)} dayIso={d} slot={slot}>
                        {cardsHere.map((a) => (
                          <ApptCard key={a.id} appt={a} />
                        ))}
                      </Cell>
                    );
                  })}
                </FragmentRow>
              ))}
            </div>
          </div>

          <DragOverlay>
            {dragging ? <ApptCardOverlay appt={dragging} /> : null}
          </DragOverlay>
        </DndContext>
      )}

      <p className="text-xs text-muted-foreground">
        Drag an appointment to another slot to reschedule. Showing{" "}
        {fmtSlot(slots[0])}–18:00, {slots.length} slots/day.
      </p>

      {/* Patient links live in the day view; keep the week grid drag-focused. */}
      <PatientLinks items={state.kind === "ready" ? state.data.items : []} />
    </div>
  );
}

// CSS grid needs the row's cells as direct children, so this is just a passthrough
// fragment (keeps the map readable without wrapping divs that would break the grid).
function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

// The local-zone day (YYYY-MM-DD) an ISO timestamp falls on.
function localDay(startIso: string): string {
  const dt = new Date(startIso);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// A compact list of the week's patients linking to their profiles — the grid
// cards are drag targets, so profile links live here to keep click vs drag clean.
function PatientLinks({ items }: { items: AppointmentListItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No appointments this week.</p>;
  }
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
      {items.map((a) => (
        <Link
          key={a.id}
          href={`/patients/${a.patient_id}`}
          className="text-muted-foreground hover:underline"
        >
          {a.patient_name}
        </Link>
      ))}
    </div>
  );
}
