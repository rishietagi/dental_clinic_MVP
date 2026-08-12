import { Suspense } from "react";
import Link from "next/link";
import { CalendarPlus } from "lucide-react";

import { CalendarView } from "./calendar-view";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";

// Calendar route. Protected by proxy.ts and by the API (active-staff on the data
// call). The app shell provides the header/nav/main.
//
// Wrapped in Suspense because the day view reads a `?date=` query param
// (useSearchParams) — the same pattern as /appointments/new and /lab/new.
export default function CalendarPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Calendar"
        subtitle="Day and week views. Drag to reschedule."
        action={
          <Link href="/appointments/new" className={buttonVariants({ size: "sm" })}>
            <CalendarPlus className="size-4" /> Schedule appointment
          </Link>
        }
      />
      <Suspense fallback={null}>
        <CalendarView />
      </Suspense>
    </div>
  );
}
