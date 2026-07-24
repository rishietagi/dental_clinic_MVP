import Link from "next/link";
import { UserPlus } from "lucide-react";

import { PatientList } from "./patient-list";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";

// Patients route. Protected by proxy.ts (any signed-in user reaches the app) and
// by the API, which enforces active-staff on the data call. The app shell provides
// the header/nav/main; this page is its content.
export default function PatientsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Patients"
        subtitle="Search by name or phone."
        action={
          <Link href="/patients/new" className={buttonVariants({ size: "sm" })}>
            <UserPlus className="size-4" /> New patient
          </Link>
        }
      />
      <PatientList />
    </div>
  );
}
