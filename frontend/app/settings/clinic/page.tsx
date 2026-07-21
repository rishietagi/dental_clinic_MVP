import { ClinicSettingsForm } from "./clinic-settings-form";
import { PageHeader } from "@/components/page-header";

// Settings > Clinic. Any signed-in staff can view; only an admin can change —
// enforced by the API (require_role("admin")). The app shell provides header/nav/main.
export default function ClinicSettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Clinic settings"
        subtitle="Clinic identity, opening hours, appointment slot length, and timezone. The calendar and appointment days are computed from these."
      />
      <ClinicSettingsForm />
    </div>
  );
}
