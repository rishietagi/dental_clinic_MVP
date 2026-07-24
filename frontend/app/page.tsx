import Link from "next/link";
import { CalendarPlus, UserPlus } from "lucide-react";

import { HealthCard } from "./health-card";
import { NeedsFollowUp } from "./needs-follow-up";
import { TodayDashboard } from "./today-dashboard";
import { TodaysCollections } from "./todays-collections";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";

// The dashboard — the app's home screen. The app shell (components/app-shell.tsx)
// provides the header, nav, and <main> now, so this page is just its sections.
// The proxy guard guarantees only signed-in users reach here.
export default function Home() {
  const todayLabel = new Date().toLocaleDateString([], {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Dashboard"
        subtitle={todayLabel}
        action={
          <>
            <Link
              href="/patients/new"
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              <UserPlus className="size-4" /> New patient
            </Link>
            <Link href="/appointments/new" className={buttonVariants({ size: "sm" })}>
              <CalendarPlus className="size-4" /> Schedule appointment
            </Link>
          </>
        }
      />

      {/* Money + attention first: today's takings and who needs a follow-up. */}
      <div className="grid gap-4 md:grid-cols-2">
        <TodaysCollections />
        <NeedsFollowUp />
      </div>

      <TodayDashboard />

      {/* System/dev card — kept, muted, last. */}
      <div className="mt-2 opacity-70">
        <HealthCard />
      </div>
    </div>
  );
}
