import Link from "next/link";

import { TreatmentList } from "./treatment-list";

// Settings > Treatments. Any signed-in staff can view the catalogue; only an
// admin can edit it — enforced by the API (require_role("admin")), with the UI
// hiding the controls as a convenience. Server shell; the list is a client
// component.
export default function TreatmentsSettingsPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <Link href="/" className="text-sm text-muted-foreground hover:underline">
        ← Dashboard
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Treatments</h1>
        <p className="text-sm text-muted-foreground">
          The procedures this clinic offers and their default prices. Invoices pick
          from this list.
        </p>
      </div>
      <TreatmentList />
    </main>
  );
}
