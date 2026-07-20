// The medical-notes banner — the one clinically important element in the app.
//
// Extracted from patient-profile.tsx in 4.4 so the profile AND the visit record
// screen render the IDENTICAL banner. It matters most while a visit is being
// recorded ("diabetic, on blood thinners" is exactly what you need in front of
// you at that moment), and two divergent copies of a safety warning is precisely
// the kind of drift worth avoiding.
//
// Renders nothing when there are no notes — an empty amber box would train
// people to ignore it.

import { TriangleAlert } from "lucide-react";

export function MedicalNotesBanner({ notes }: { notes: string | null }) {
  if (!notes || !notes.trim()) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    >
      <TriangleAlert className="mt-0.5 size-5 shrink-0" />
      <div>
        <p className="font-medium">Medical notes</p>
        <p className="whitespace-pre-wrap text-sm">{notes}</p>
      </div>
    </div>
  );
}
