import { Suspense } from "react";

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
    <div className="w-full">
      <Suspense fallback={null}>
        <VisitForm patientId={id} />
      </Suspense>
    </div>
  );
}
