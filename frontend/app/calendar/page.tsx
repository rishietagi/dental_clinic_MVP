import Link from "next/link";
import { CalendarPlus } from "lucide-react";

import { CalendarView } from "./calendar-view";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";

// Calendar route. Protected by proxy.ts and by the API (active-staff on the data
// call). The app shell provides the header/nav/main.
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
      <CalendarView />
    </div>
  );
}
