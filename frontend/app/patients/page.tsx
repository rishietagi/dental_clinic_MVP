import { PatientList } from "./patient-list";

// Patients route. Protected by proxy.ts (any signed-in user reaches the app) and
// by the API, which enforces active-staff on the data call. Server shell; the
// interactive search + list live in the client component.
export default function PatientsPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Patients</h1>
      <PatientList />
    </main>
  );
}
