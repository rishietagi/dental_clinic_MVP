import { ReportsView } from "./reports-view";
import { PageHeader } from "@/components/page-header";

// Reports route (6.1) — the owner's "how's the practice doing" screen. Guarded by
// proxy.ts (signed-in) and the API (dentist/admin). Shell provides header/nav/main.
export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Reports" subtitle="Revenue, procedure mix, and no-shows." />
      <ReportsView />
    </div>
  );
}
