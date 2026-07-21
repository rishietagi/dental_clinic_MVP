import { HealthCard } from "./health-card";
import { NeedsFollowUp } from "./needs-follow-up";
import { RoleNav } from "./role-nav";
import { SignOutButton } from "./sign-out-button";
import { TodayDashboard } from "./today-dashboard";
import { TodaysCollections } from "./todays-collections";
import { createClient } from "@/lib/supabase/server";

// The dashboard — the app's home screen (step 3.6). The proxy guard guarantees
// only signed-in users get here, so reading the user is safe. Async server
// component: it reads the session on the server; the schedule itself loads in the
// client component below.
export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Rendered on the server, so this is the server's date — it's a heading only;
  // the schedule itself uses the browser's "today" (see the timezone note in LOG).
  const todayLabel = new Date().toLocaleDateString([], {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm text-muted-foreground">{user?.email}</span>
        <SignOutButton />
      </div>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dental Clinic</h1>
        <p className="text-sm text-muted-foreground">{todayLabel}</p>
      </div>

      <RoleNav />

      {/* Highest-value first: who's mid-treatment with no next appointment. */}
      <NeedsFollowUp />

      <TodayDashboard />

      {/* The owner's-eye money figure, alongside the day's operational view. */}
      <TodaysCollections />

      {/* System/dev card — kept, but last so the clinical content leads. */}
      <div className="mt-2 opacity-80">
        <HealthCard />
      </div>
    </main>
  );
}
