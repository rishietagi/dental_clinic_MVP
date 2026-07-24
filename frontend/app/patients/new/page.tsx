import { NewPatientForm } from "./new-patient-form";
import { PageHeader } from "@/components/page-header";

// New patient route (6.3). Any active staff can register a patient. The app shell
// provides header/nav; this page holds a narrow form.
export default function NewPatientPage() {
  return (
    <div className="mx-auto w-full max-w-xl">
      <PageHeader title="New patient" subtitle="Register a patient in the clinic." />
      <div className="mt-6">
        <NewPatientForm />
      </div>
    </div>
  );
}
