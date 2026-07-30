import { Suspense } from "react";

import { SendToLabForm } from "./send-to-lab-form";

// Send a sample to the lab (6.6). A plain page (not a modal) so it matches
// /patients/new and /appointments/new, and so a visit or appointment can deep-link
// into it with the patient/visit/appointment prefilled. useSearchParams needs a
// Suspense boundary in Next 16.
export default function SendToLabPage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <Suspense fallback={null}>
        <SendToLabForm />
      </Suspense>
    </div>
  );
}
