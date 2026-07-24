import { PatientProfile } from "./patient-profile";

// Patient profile route (the app's first dynamic route). Guarded by proxy.ts
// (signed-in) and by the API (staff) on the data call. In Next 16 `params` is a
// Promise. The id is a PATH segment — allowed; the rule bans ids in query strings.
export default async function PatientProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="w-full">
      <PatientProfile patientId={id} />
    </div>
  );
}
