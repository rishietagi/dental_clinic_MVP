import Link from "next/link";
import { CalendarPlus, UserPlus } from "lucide-react";

import { HealthCard } from "./health-card";
import { LabDashboardCard } from "./lab-dashboard";
import { NeedsFollowUp } from "./needs-follow-up";
import { TodayDashboard } from "./today-dashboard";
import { TodaysCollections } from "./todays-collections";
import {
  DueForCheckUpCard,
  NothingRecordedCard,
  ToBillCard,
} from "./worklists";
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
      <PageHeader title="Dashboard" subtitle={todayLabel} />

      {/* Primary actions: big, centred, colour-shift on hover. */}
      <div className="flex flex-col justify-center gap-4 sm:flex-row">
        <Link
          href="/patients/new"
          className="flex flex-1 items-center justify-center gap-2.5 rounded-xl border border-input bg-card px-6 py-5 text-base font-medium shadow-xs transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground sm:max-w-xs"
        >
          <UserPlus className="size-5" /> Add new patient
        </Link>
        <Link
          href="/appointments/new"
          className="flex flex-1 items-center justify-center gap-2.5 rounded-xl bg-primary px-6 py-5 text-base font-medium text-primary-foreground shadow-sm transition-colors hover:bg-secondary hover:text-secondary-foreground sm:max-w-xs"
        >
          <CalendarPlus className="size-5" /> New appointment
        </Link>
      </div>

      {/* Operational view first: today's schedule, then who needs a follow-up,
          then today's takings. */}
      <TodayDashboard />

      {/* Work the clinic still owes someone (6.8). Each hides itself when clear,
          so an up-to-date day shows none of them. Billing first: it's money. */}
      <ToBillCard />
      <NothingRecordedCard />
      <DueForCheckUpCard />

      {/* Lab work needing attention — hides itself when there's nothing due. */}
      <LabDashboardCard />

      <div className="grid gap-4 md:grid-cols-2">
        <NeedsFollowUp />
        <TodaysCollections />
      </div>

      {/* System/dev card — kept, muted, last. */}
      <div className="mt-2 opacity-70">
        <HealthCard />
      </div>
    </div>
  );
}
