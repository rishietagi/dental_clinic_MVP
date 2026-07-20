import Link from "next/link";

import { ClinicSettingsForm } from "./clinic-settings-form";

// Settings > Clinic. Any signed-in staff can view the settings; only an admin can
// change them — enforced by the API (require_role("admin")), with the UI hiding
// the controls as a convenience. Server shell; the form is a client component.
export default function ClinicSettingsPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <Link href="/" className="text-sm text-muted-foreground hover:underline">
        ← Dashboard
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Clinic settings</h1>
        <p className="text-sm text-muted-foreground">
          Opening hours, appointment slot length, and the clinic’s timezone. The
          calendar and appointment days are computed from these.
        </p>
      </div>
      <ClinicSettingsForm />
    </main>
  );
}
