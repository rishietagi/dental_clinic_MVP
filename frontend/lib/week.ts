// Date/slot helpers for the calendar, in the CLINIC's timezone (step 4.9).
//
// Before 4.9 these read the browser's local zone (`dt.getHours()`, `new
// Date(y,m,d,...)`) and hardcoded 09:00–18:00 / 30-min slots. Now the clinic
// hours + slot size come from clinic settings, and all "which day / which slot"
// math is done in the clinic's IANA timezone via date-fns-tz — so an appointment
// lands on the right day and slot regardless of where the viewer's browser is.
//
// Calendar "day" strings are still YYYY-MM-DD *clinic-local* wall dates; the grid
// columns and headers are built from them.

import { formatInTimeZone, fromZonedTime, toZonedTime } from "date-fns-tz";

// Historical defaults, still used as the fallback when settings haven't loaded.
export const DAY_START_HOUR = 9;
export const DAY_END_HOUR = 18; // exclusive upper bound of the last slot's start
export const SLOT_MIN = 30;

export type Slot = { hour: number; minute: number };

// The ordered slots of a clinic day, from the configured hours + slot size.
export function daySlots(
  openHour = DAY_START_HOUR,
  closeHour = DAY_END_HOUR,
  slotMin = SLOT_MIN,
): Slot[] {
  const slots: Slot[] = [];
  for (let h = openHour; h < closeHour; h++) {
    for (let m = 0; m < 60; m += slotMin) {
      slots.push({ hour: h, minute: m });
    }
  }
  return slots;
}

// --- clinic-zone wall-date helpers ------------------------------------------

// The YYYY-MM-DD clinic-local date an ISO instant falls on.
export function clinicDay(startIso: string, tz: string): string {
  return formatInTimeZone(new Date(startIso), tz, "yyyy-MM-dd");
}

// Today's date (YYYY-MM-DD) in the clinic zone.
export function todayIso(tz: string): string {
  return formatInTimeZone(new Date(), tz, "yyyy-MM-dd");
}

// The slot an appointment's start falls into, in the CLINIC zone. Returns null
// if outside the day window (still listed elsewhere, just not placed on the grid).
export function slotForStart(
  startIso: string,
  tz: string,
  openHour = DAY_START_HOUR,
  closeHour = DAY_END_HOUR,
  slotMin = SLOT_MIN,
): Slot | null {
  const zoned = toZonedTime(new Date(startIso), tz); // a Date whose fields read as clinic-local
  const hour = zoned.getHours();
  const minute = zoned.getMinutes() < slotMin ? 0 : slotMin;
  if (hour < openHour || hour >= closeHour) return null;
  return { hour, minute };
}

// The UTC instant (ISO) of a given clinic day + slot — for rescheduling: the
// clinic-local wall time is converted back to a real instant via fromZonedTime.
export function slotInstant(dayIso: string, slot: Slot, tz: string): string {
  const wall = `${dayIso}T${String(slot.hour).padStart(2, "0")}:${String(
    slot.minute,
  ).padStart(2, "0")}:00`;
  return fromZonedTime(wall, tz).toISOString();
}

// Format an ISO instant as HH:MM in the clinic zone.
export function fmtTimeInZone(startIso: string, tz: string): string {
  return formatInTimeZone(new Date(startIso), tz, "HH:mm");
}

// --- pure YYYY-MM-DD arithmetic (zone-independent wall-date math) ------------
// These operate on wall dates as plain strings; no instant is involved, so
// browser-local Date construction at noon (DST-safe) is fine.

function isoFromParts(y: number, m: number, d: number): string {
  const dt = new Date(y, m - 1, d, 12, 0, 0);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

// Monday of the week containing the given YYYY-MM-DD (ISO weeks start Monday).
export function startOfWeek(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d, 12, 0, 0);
  const dow = dt.getDay(); // 0 = Sun … 6 = Sat
  const backToMonday = (dow + 6) % 7;
  dt.setDate(dt.getDate() - backToMonday);
  return isoFromParts(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
}

// The 7 day-columns (Mon..Sun) of the week starting at `weekStartIso`.
export function weekDays(weekStartIso: string): string[] {
  const [y, m, d] = weekStartIso.split("-").map(Number);
  return Array.from({ length: 7 }, (_, i) => isoFromParts(y, m, d + i));
}

// Shift a YYYY-MM-DD by whole weeks.
export function addWeeks(iso: string, weeks: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return isoFromParts(y, m, d + weeks * 7);
}

// --- cell ids + formatting ---------------------------------------------------

export function cellId(dayIso: string, slot: Slot): string {
  return `${dayIso}T${String(slot.hour).padStart(2, "0")}:${String(slot.minute).padStart(2, "0")}`;
}

export function parseCellId(id: string): { dayIso: string; slot: Slot } {
  const [dayIso, hm] = id.split("T");
  const [hour, minute] = hm.split(":").map(Number);
  return { dayIso, slot: { hour, minute } };
}

export function fmtSlot(slot: Slot): string {
  return `${String(slot.hour).padStart(2, "0")}:${String(slot.minute).padStart(2, "0")}`;
}

// Short day-column header, e.g. "Mon 21".
export function fmtDayHeader(dayIso: string): string {
  const [y, m, d] = dayIso.split("-").map(Number);
  const dt = new Date(y, m - 1, d, 12, 0, 0);
  const weekday = dt.toLocaleDateString([], { weekday: "short" });
  return `${weekday} ${d}`;
}
