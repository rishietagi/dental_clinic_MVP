import Link from "next/link";

import { DayView } from "./day-view";

// Calendar route. Protected by proxy.ts (any signed-in user reaches the app) and
// by the API (active-staff on the data call). Server shell; the interactive day
// view lives in the client component.
export default function CalendarPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <Link href="/" className="text-sm text-muted-foreground hover:underline">
        ← Dental Clinic
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Calendar</h1>
      <DayView />
    </main>
  );
}
