import { ReportsView } from "./reports-view";

// Reports route (step 6.1) — the owner's "how's the practice doing" screen.
// Guarded by proxy.ts (signed-in) and the API (dentist/admin) on the data call.
export default function ReportsPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
      <ReportsView />
    </main>
  );
}
