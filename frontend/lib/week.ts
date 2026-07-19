// Pure date helpers for the week-view calendar. All dates are handled as
// YYYY-MM-DD strings (local-zone wall dates) or Date objects in the browser's
// local zone — consistent with the day view. See the timezone caveat in the LOG:
// the clinic zone isn't configurable until Phase 4.

// The clinic day window and slot size are HARDCODED for now. Configurable clinic
// hours / slot duration are Phase 4 (clinic settings).
export const DAY_START_HOUR = 9;
export const DAY_END_HOUR = 18; // exclusive upper bound of the last slot's start
export const SLOT_MIN = 30;

export type Slot = { hour: number; minute: number };

// The ordered time slots of a clinic day (09:00, 09:30, … 17:30).
export function daySlots(): Slot[] {
  const slots: Slot[] = [];
  for (let h = DAY_START_HOUR; h < DAY_END_HOUR; h++) {
    for (let m = 0; m < 60; m += SLOT_MIN) {
      slots.push({ hour: h, minute: m });
    }
  }
  return slots;
}

// Format a YYYY-MM-DD string from a local Date.
export function isoDate(dt: Date): string {
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function todayIso(): string {
  return isoDate(new Date());
}

// Monday of the week containing the given YYYY-MM-DD (ISO weeks start Monday).
export function startOfWeek(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d, 12, 0, 0); // local noon dodges DST edges
  const dow = dt.getDay(); // 0 = Sun … 6 = Sat
  const backToMonday = (dow + 6) % 7; // Mon->0, Sun->6
  dt.setDate(dt.getDate() - backToMonday);
  return isoDate(dt);
}

// The 7 day-columns (Mon..Sun) of the week starting at `weekStartIso`.
export function weekDays(weekStartIso: string): string[] {
  const [y, m, d] = weekStartIso.split("-").map(Number);
  return Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(y, m - 1, d + i, 12, 0, 0);
    return isoDate(dt);
  });
}

// Shift a YYYY-MM-DD by whole weeks.
export function addWeeks(iso: string, weeks: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + weeks * 7, 12, 0, 0);
  return isoDate(dt);
}

// A local Date at a given day (YYYY-MM-DD) + slot time.
export function slotDate(dayIso: string, slot: Slot): Date {
  const [y, m, d] = dayIso.split("-").map(Number);
  return new Date(y, m - 1, d, slot.hour, slot.minute, 0, 0);
}

// The slot an appointment's start_time falls into, in the browser's local zone.
// Returns null if it's outside the rendered day window (still listed elsewhere;
// just not placed on the grid).
export function slotForStart(startIso: string): Slot | null {
  const dt = new Date(startIso);
  const hour = dt.getHours();
  const minute = dt.getMinutes() < SLOT_MIN ? 0 : SLOT_MIN;
  if (hour < DAY_START_HOUR || hour >= DAY_END_HOUR) return null;
  return { hour, minute };
}

// A stable key for a (day, slot) cell — used as the droppable id.
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
