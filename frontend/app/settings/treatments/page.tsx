import { TreatmentList } from "./treatment-list";
import { PageHeader } from "@/components/page-header";

// Settings > Treatments. Any signed-in staff can view the catalogue; only an admin
// can edit it — enforced by the API (require_role("admin")), the UI hiding controls
// as convenience. The app shell provides the header/nav/main.
export default function TreatmentsSettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Treatments"
        subtitle="The procedures this clinic offers and their default prices. Invoices pick from this list."
      />
      <TreatmentList />
    </div>
  );
}
