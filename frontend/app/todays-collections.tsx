"use client";

// Dashboard section (step 5.5): today's collections.
//
// The owner's-eye money figure (BUILD_PLAN §5.4): how much came in today, with a
// per-mode breakdown, so the owner can reconcile against the drawer. "Today" is the
// clinic-local day — the backend computes it from clinic_settings.timezone.
//
// ADMIN-ONLY as of 6.12. This is the practice's takings, not one patient's bill, so
// it moved behind the admin login alongside the Reports page. GET /invoices/collections
// is require_role("admin") — that is the real guard; hiding the card just avoids
// showing every receptionist a 403.
//
// The role check lives in an outer component so the inner one can call the fetch
// hook unconditionally (hooks can't be skipped). Money is formatted from the decimal
// string via formatMoney — never float arithmetic.

import { formatMoney, useTodaysCollections } from "@/lib/use-invoices";
import { useCurrentStaff } from "@/lib/use-current-staff";

const MODE_LABELS: Record<string, string> = {
  cash: "Cash",
  card: "Card",
  upi: "UPI",
};

export function TodaysCollections() {
  const staffState = useCurrentStaff();

  // Render nothing at all for non-admins — including while roles are still
  // loading, so the card never flashes in and then vanishes.
  if (staffState.kind !== "staff" || !staffState.staff.roles.includes("admin")) {
    return null;
  }

  return <CollectionsCard />;
}

function CollectionsCard() {
  const state = useTodaysCollections();

  return (
    <section className="flex w-full flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight">Today’s collections</h2>

      {state.kind === "loading" && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {state.kind === "error" && (
        <p className="text-sm text-destructive">
          Couldn’t load collections: {state.message}
        </p>
      )}

      {state.kind === "ready" && (
        <div className="rounded-lg border p-4">
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-semibold tabular-nums">
              {formatMoney(state.data.total)}
            </span>
            <span className="text-sm text-muted-foreground">
              {state.data.count} {state.data.count === 1 ? "payment" : "payments"}
            </span>
          </div>

          {state.data.count === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">
              No payments taken yet today.
            </p>
          ) : (
            <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {Object.entries(state.data.by_mode).map(([mode, amount]) => (
                <div key={mode} className="flex items-center gap-2">
                  <dt className="text-muted-foreground">{MODE_LABELS[mode] ?? mode}</dt>
                  <dd className="tabular-nums">{formatMoney(amount)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </section>
  );
}
