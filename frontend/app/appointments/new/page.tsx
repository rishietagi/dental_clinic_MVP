import { Suspense } from "react";

import { NewAppointmentForm } from "./new-appointment-form";
import { PageHeader } from "@/components/page-header";

// Schedule-appointment route (6.3) — the app's core action, finally a standalone
// screen (before this, appointments were only bookable inline from a visit). Any
// active staff can book. Wrapped in Suspense because the form reads a ?patient=
// query param (useSearchParams).
export default function NewAppointmentPage() {
  return (
    <div className="mx-auto w-full max-w-xl">
      <PageHeader title="Schedule appointment" subtitle="Book a slot for a patient." />
      <div className="mt-6">
        <Suspense fallback={null}>
          <NewAppointmentForm />
        </Suspense>
      </div>
    </div>
  );
}
