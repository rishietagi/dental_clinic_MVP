"use client";

// Dashboard section (step 4.8): open treatments with no upcoming appointment.
//
// BUILD_PLAN §3 calls this the single most valuable report in the app — a
// patient mid-course whom nobody has booked back in is revenue walking out the
// door. It sits at the TOP of the dashboard because it's the highest-value thing
// to see first. Each row links to the patient so the follow-up can be booked.
//
// Reads GET /treatments/needs-follow-up (clinic-wide). A treatment is listed
// when it's in_progress and has no future non-cancelled appointment.

import Link from "next/link";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { useNeedsFollowUp } from "@/lib/use-treatments";
import { formatVisitDate } from "@/lib/use-visits";

export function NeedsFollowUp() {
  const state = useNeedsFollowUp();

  return (
    <section className="flex w-full flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight">
        Treatments needing a follow-up
      </h2>

      {state.kind === "loading" && <LoadingState label="Loading…" />}

      {state.kind === "error" && (
        <ErrorState message={`Couldn’t load the report: ${state.message}`} />
      )}

      {state.kind === "ready" && state.data.total === 0 && (
        <EmptyState
          title="All caught up"
          hint="Every open treatment has a follow-up booked."
        />
      )}

      {state.kind === "ready" && state.data.total > 0 && (
        <div className="overflow-x-auto rounded-lg border border-amber-300 dark:border-amber-800">
          <table className="w-full text-sm">
            <thead className="border-b bg-amber-50 text-left text-amber-900 dark:bg-amber-950 dark:text-amber-100">
              <tr>
                <th className="px-3 py-2 font-medium">Patient</th>
                <th className="px-3 py-2 font-medium">Treatment</th>
                <th className="px-3 py-2 font-medium">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {state.data.items.map((t) => (
                <tr key={t.id} className="border-b last:border-0">
                  <td className="px-3 py-2">
                    <Link
                      href={`/patients/${t.patient_id}`}
                      className="font-medium hover:underline"
                    >
                      {t.patient_name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {t.title}
                    {t.tooth_ref && (
                      <span className="text-muted-foreground"> · tooth {t.tooth_ref}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">
                    {t.last_visit_date
                      ? formatVisitDate(t.last_visit_date)
                      : "no visits yet"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
