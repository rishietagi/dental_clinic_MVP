import { ReportsView } from "./reports-view";
import { PageHeader } from "@/components/page-header";

// Reports route (6.1) — the owner's "how's the practice doing" screen. Guarded by
// proxy.ts (signed-in) and the API (**admin only** as of 6.12). The nav item hides
// for non-admins, but the route is still reachable by typing the URL, so ReportsView
// renders a calm "not for this login" state on a 403. Shell provides header/nav/main.
export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Reports" subtitle="Revenue, procedure mix, and no-shows." />
      <ReportsView />
    </div>
  );
}
