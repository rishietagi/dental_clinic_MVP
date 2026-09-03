import { PageHeader } from "@/components/page-header";

// Reports route (6.1) — HIDDEN in 10.2.
//
// The nav item is commented out in components/app-shell.tsx, but the route stays
// reachable by typing the URL, so it renders an explanatory stub rather than a
// working screen. The BACKEND is completely untouched: GET /reports, its service
// and all its tests still work, so restoring this page means putting the nav item
// back and returning <ReportsView /> below (the component is still in this folder).
//
// Why hidden: the app runs on one shared PC at the front desk. Until 10.1 the
// practice's revenue sat behind an admin login (6.12); with no login and one
// shared machine, a role gate cannot keep it private.
export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Reports" subtitle="Not available in this version." />
      <p className="text-sm text-muted-foreground">
        Practice reports are turned off in the desktop version of the app.
      </p>
    </div>
  );
}
