import { VisitForm } from "./visit-form";

// Visit record route (step 4.4) — the screen Phase 4 exists for.
//
// Nested under the patient because the patient is always known first: the
// dentist opens the profile, sees the medical-notes banner, then records. Same
// server-shell pattern as the profile page; `params` is a Promise in Next 16.
export default async function NewVisitPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-8">
      <VisitForm patientId={id} />
    </main>
  );
}
