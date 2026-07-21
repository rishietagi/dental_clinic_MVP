import { PatientList } from "./patient-list";
import { PageHeader } from "@/components/page-header";

// Patients route. Protected by proxy.ts (any signed-in user reaches the app) and
// by the API, which enforces active-staff on the data call. The app shell provides
// the header/nav/main; this page is its content.
export default function PatientsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Patients" subtitle="Search by name or phone." />
      <PatientList />
    </div>
  );
}
